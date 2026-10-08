"""The CV screening workflow (the "Pre-interview subgraph" of the architecture, Figure 3). One run per CV.

    START -> parse_cv -> validate_extraction --valid--------------------------> extract_profile
                              |      ^                                            |   ^
                              |      | (once)                        bad answer,  |   | once more
                              |   ocr_once <--not valid, PDF, 1st try             v   |
                              |                                            (check the answer)
                              `--not valid after OCR, or not English--.           |
                                                                      v           v
                                                               needs_review   match_requirements
                                                                      |           |
                                                                      |           v
                                                                      |     justifications --needs review--.
                                                                      |           | passed / excluded      |
                                                                      |           v                        |
                                                                      |     score_sections (F4)            |
                                                                      |           v                        |
                                                                      |     check_quotes                   |
                                                                      |           v                        |
                                                                      |     ats_match                      |
                                                                      |           v                        |
                                                                      |     combine_score                  |
                                                                      |           v                        |
                                                                      `---> save_result <------------------'
                                                                                  |
                                                                                  v
                                              .------------------------->  hr_review   (PAUSE: waits for a person)
                                              |                                   |  Include / Exclude / Undo, optional note
                                              `-------------------------- apply_decision

    parse_cv              PYTHON      the text out of the saved PDF / DOCX / DOC / TXT file
    validate_extraction   PYTHON      enough text? not garbled? English only?
    ocr_once              AI VISION   Gemini reads the PDF pages like pictures (a scanned CV). Only once
    needs_review          PYTHON      the reason is saved; the file is kept, so it can be screened again
    extract_profile       AI          ONE call: skills, work history, education, years, and whether the education
                                      meets the job's qualification (email and phone are removed first)
    match_requirements    PYTHON      each requirement: Met / Partially met / Unmet, how we know and words from the CV.
                                      Code first (skill names); then the AI's judgement by meaning from extract_profile,
                                      kept only if its words are really in the CV. Years by code (75% = partly met)
    justifications        PYTHON      the fixed rule: a must-have Unmet -> excluded, with the reason; otherwise included
                                      (Partially met is not missing: it is named in the reason)
    score_sections        AI          F4, ONE call: skills, experience and qualifications, each 0-100 + reason + quote
    check_quotes          PYTHON      a quote that is not really in the CV is removed ("no proof")
    ats_match             PYTHON      ATS match score: share of the job's ATS keywords found in the CV (made once per job)
    combine_score         PYTHON      weighted score = the three scores with the job's weights (the AI never sees them)
    save_result           PYTHON + DB the result, the scores and the text it used (screening_result only; the
                                      candidate table is never changed by the screening) + one row in workflow_run
    hr_review             PERSON      the run pauses here (LangGraph interrupt) until the interviewer includes or
                                      excludes the candidate. The paused run is kept by the checkpointer (PostgreSQL),
                                      so it survives a restart and can be continued days later
    apply_decision        PYTHON + DB saves the person's decision (who, when, optional note), then waits again in
                                      hr_review, so the decision can be changed or undone at any time

The system result (passed / excluded / needs review) is never overwritten by the person's decision: both are
kept, and the page shows the decision when there is one. Screening a CV again lets the system decide again: the
old decision is cleared (and written to workflow_run), and the person can change it again.
AI calls per CV: 2 (extract_profile, score_sections). A scanned PDF adds 1 (ocr_once); a bad profile answer is
asked once more. The free Gemini key limits the number of calls per day (see ai_calls in the log).
The AI reads and suggests; Python checks, calculates and decides. Each run saves its own result at the end,
so if the backend stops, only the CV that was running has to be screened again.
Still to come (see the architecture): partial matches with CV quotes (semantic ranking) and the ranking.
"""
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ValidationError, field_validator
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json, llm_read_pdf
from app.core import config
from app.core.database import engine
from app.features.candidates.services.cv_reading_service import looks_english, text_problem
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.features.screening.services.score_service import SECTIONS, weighted_score
from app.graphs.checkpointer import checkpointer
from app.graphs.cv_screening_prompts import EXTRACT_PROFILE_PROMPT, OCR_PROMPT, SCORE_SECTIONS_PROMPT
from app.utils.file_text_utils import read_file_text
from app.utils.skill_names import find_skill

log = logging.getLogger("cv_screening_graph")

MAX_OCR_TRIES = 1                # the AI reads a weak PDF at most once
MAX_PROFILE_TRIES = 2            # the AI is asked at most twice for the profile of one CV
MAX_CV_CHARS = 15000             # about six pages; more is cut off before it goes to the AI


class CvScreenState(TypedDict):
    thread_id: str         # this run's id in the checkpointer (saved on the result, to continue it later)
    review_only: bool      # True: the CV is already screened; go straight to hr_review (see decide())
    decision: dict         # what the person answered in hr_review: {decision, note, by}
    candidate_id: int
    job_id: int
    job: dict              # title, required_skills, preferred_skills, min_years, qualifications, weights
    file_path: str         # the saved CV file on this computer ("" if there is none)
    text: str              # the text read from the file
    pages: int
    text_source: str       # file (read by code) | ai_read (read by the AI from the PDF) | ""
    problem: str           # why the text cannot be used ("" = fine)
    ocr_tries: int
    english: bool
    clean_text: str        # the text without email addresses and phone numbers (what the AI gets)
    profile: dict          # what the AI read from the CV: skills, total_years, education, experience, language
    profile_tries: int
    ai_calls: int          # how many times this run asked Gemini (written to the log)
    matches: list          # one entry per requirement: {requirement, kind, status, met, how, evidence}
                           #   status: met | partial | unmet | unchecked;  met: True (met/partial), False, None
    missing: list          # the must-haves that are not met
    sections: dict         # F4: {"skills": {score, reason, quote, proof}, "experience": ..., "qualifications": ...}
    weighted_score: float | None
    ats: dict              # ATS match: {score 0-100, matched: [...], missing: [...], total}
    result: str            # passed | excluded | needs_review
    reason: str            # one sentence for the interviewer
    error: str
    started: float


# ---------- helpers ----------

class Profile(BaseModel):
    """The shape extract_profile must get back from the AI. A wrong shape makes it ask the AI once more."""
    skills: list[str] = []
    total_years: float = 0
    education: list[dict] = []
    experience: list[dict] = []
    language: str = "en"
    requirement_checks: list[dict] = []    # the AI's view per requirement: {requirement, status, evidence}
    qualification_status: str | None = None   # met | partial | unmet | None (no qualification asked)
    qualification_reason: str = ""

    @field_validator("skills")
    @classmethod
    def short_names(cls, skills: list[str]) -> list[str]:
        cleaned = [str(s).strip()[:60] for s in skills if str(s).strip()]
        return list(dict.fromkeys(cleaned))[:80]

    @field_validator("total_years")
    @classmethod
    def sensible_years(cls, years: float) -> float:
        return max(0.0, min(60.0, round(float(years), 1)))


PHONE = re.compile(r"(?<![\w+(])(?:\(\+?\d{2,4}\)|\+?\d{2,4})[\s-]?\d{3,5}[\s-]?\d{3,7}(?!\d)")   # +880 1700-000001


def remove_contacts(text: str) -> str:
    """Email addresses and phone numbers are not needed to judge a CV, so the AI never sees them.
    Years like "2019 - 2023" are kept: they are needed to count the years of experience."""
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", text)
    return PHONE.sub(lambda m: "[phone]" if 9 <= sum(c.isdigit() for c in m.group(0)) <= 15 else m.group(0), text)


def _degree_names(education: list[dict]) -> list[str]:
    return [str(item.get("degree") or "").strip() for item in education if str(item.get("degree") or "").strip()]


# ---------- nodes ----------

def parse_cv(state: CvScreenState) -> dict:
    path = Path(state["file_path"]) if state["file_path"] else None
    if not path or not path.is_file():
        return {"problem": "No CV file is saved for this candidate."}
    try:
        text, pages = read_file_text(path.name, path.read_bytes())
    except ValueError as problem:
        return {"problem": f"The CV text could not be read: {problem}"}
    return {"text": text, "pages": pages, "text_source": "file" if text else ""}


def validate_extraction(state: CvScreenState) -> dict:
    if state["problem"] and not state["text"]:              # parse_cv found no usable file at all
        return {}
    problem = text_problem(state["text"], state["pages"]) if Path(state["file_path"]).suffix.lower() != ".txt" else ""
    if not problem and not state["text"].strip():
        problem = "The CV file is empty."
    english = looks_english(state["text"]) if not problem else True
    return {"problem": problem, "english": english}


def ocr_once(state: CvScreenState) -> dict:
    text = llm_read_pdf(OCR_PROMPT, Path(state["file_path"]).read_bytes())
    tried = {"ocr_tries": state["ocr_tries"] + 1, "ai_calls": state["ai_calls"] + 1}
    if not text:
        return {**tried, "error": last_error()}
    return {**tried, "text": text, "pages": 1, "text_source": "ai_read"}


def needs_review(state: CvScreenState) -> dict:
    if state["problem"]:
        reason = state["problem"]
        if state["ocr_tries"]:
            reason += " The AI could not read the file either" + (f" ({state['error']})." if state["error"] else ".")
        return {"result": "needs_review", "reason": "The CV text may be incomplete: " + reason}
    if not state["english"]:
        return {"result": "needs_review", "reason": "The CV is not written in English. A person should look at it."}
    return {"result": "needs_review", "reason": f"The AI could not read the CV into a profile: {state['error']}."}


def extract_profile(state: CvScreenState) -> dict:
    clean = remove_contacts(state["text"])[:MAX_CV_CHARS]
    job = state["job"]
    answer = llm_json(EXTRACT_PROFILE_PROMPT, {"cv": clean, "requirements": job["required_skills"] + job["preferred_skills"],
                                               "required_qualification": job["qualifications"]})
    tried = {"clean_text": clean, "profile_tries": state["profile_tries"] + 1, "ai_calls": state["ai_calls"] + 1}
    if answer is None:
        return {**tried, "profile": {}, "error": last_error()}
    try:
        return {**tried, "profile": Profile(**answer).model_dump(), "error": ""}
    except (ValidationError, TypeError, ValueError):
        return {**tried, "profile": {}, "error": "the AI's answer did not have the right fields"}


def _in_cv(state: CvScreenState, words: str) -> bool:
    """Are these exact words in the CV? (The AI saw the text without email and phone.)"""
    return bool(words.strip()) and any(_plain(words) in _plain(text) for text in (state["text"], state["clean_text"]))


def _match(requirement: str, kind: str, status: str, how: str, evidence: str = "") -> dict:
    met = {"met": True, "partial": True, "unmet": False}.get(status)          # partial is not "missing"
    return {"requirement": requirement, "kind": kind, "status": status, "met": met, "how": how, "evidence": evidence}


def match_requirements(state: CvScreenState) -> dict:
    """Met / Partially met / Unmet for every requirement, with how we know.
    1. Code first: the skill (or another name of it) is in the CV -> met.
    2. Otherwise the AI's judgement by meaning from extract_profile, but only with words that are really in the CV.
    3. Years: code. 75% or more of the minimum counts as partly met (2.5 of 3 years).
    4. Qualification: the AI's judgement from extract_profile."""
    job, profile = state["job"], state["profile"]
    ai_view = {str(c.get("requirement", "")).strip().lower(): c for c in profile["requirement_checks"] if isinstance(c, dict)}
    matches = []
    for kind, skills in (("must", job["required_skills"]), ("nice", job["preferred_skills"])):
        for skill in skills:
            how = find_skill(skill, profile["skills"], state["text"])
            if how:
                matches.append(_match(skill, kind, "met", how))
                continue
            check = ai_view.get(skill.strip().lower(), {})
            status, evidence = str(check.get("status") or "unmet").lower(), str(check.get("evidence") or "").strip()[:300]
            if status in ("met", "partial") and _in_cv(state, evidence):
                word = "means the same" if status == "met" else "is close, not the same"
                matches.append(_match(skill, kind, status, f"the AI found that the CV {word}", evidence))
            else:
                matches.append(_match(skill, kind, "unmet", "not found in the CV"))

    if job["min_years"]:
        years, minimum = profile["total_years"], job["min_years"]
        status = "met" if years >= minimum else "partial" if years >= 0.75 * minimum else "unmet"
        matches.append(_match(f"{minimum}+ years of experience", "must", status, f"the CV shows about {years:g} years"))

    if job["qualifications"]:                          # judged by the AI in extract_profile (same call)
        status = str(profile["qualification_status"] or "").lower()
        if status in ("met", "partial", "unmet"):
            how = profile["qualification_reason"].strip()[:200] or ", ".join(_degree_names(profile["education"]))
            matches.append(_match(job["qualifications"], "must", status, how))
        else:
            matches.append(_match(job["qualifications"], "must", "unchecked", "the AI did not answer this question"))

    missing = [m["requirement"] for m in matches if m["kind"] == "must" and m["status"] == "unmet"]
    return {"matches": matches, "missing": missing}


def justifications(state: CvScreenState) -> dict:
    """The fixed rule. The AI never decides."""
    if not str(state["profile"]["language"]).lower().startswith("en"):
        return {"result": "needs_review", "reason": "The CV is not written in English. A person should look at it."}
    if state["missing"]:
        return {"result": "excluded", "reason": "Missing must-have: " + "; ".join(state["missing"]) + "."}
    if any(m["status"] == "unchecked" for m in state["matches"]):
        return {"result": "needs_review", "reason": "One requirement could not be checked. A person should look at it."}
    must = [m for m in state["matches"] if m["kind"] == "must"]
    partly = [m["requirement"] for m in must if m["status"] == "partial"]
    if partly:                                         # not missing, so not excluded; the reason says what is only close
        return {"result": "passed", "reason": f"No must-have is missing. Partially met: {'; '.join(partly)}."}
    return {"result": "passed", "reason": f"All {len(must)} must-have requirement(s) are met."}


def score_sections(state: CvScreenState) -> dict:
    job = {key: state["job"][key] for key in ("title", "required_skills", "preferred_skills", "min_years", "qualifications")}
    answer = llm_json(SCORE_SECTIONS_PROMPT, {"job": job, "cv": state["clean_text"]})
    calls = state["ai_calls"] + 1
    if not isinstance(answer, dict):
        return {"ai_calls": calls, "sections": {}, "error": "the AI could not score the CV: " + last_error()}
    sections = {}
    for name in SECTIONS:
        part = answer.get(name) if isinstance(answer.get(name), dict) else {}
        try:
            score = max(0, min(100, round(float(part.get("score")))))
        except (TypeError, ValueError):
            score = None                              # no usable number: this section has no score
        sections[name] = {"score": score, "reason": str(part.get("reason") or "").strip()[:300],
                          "quote": str(part.get("quote") or "").strip()[:300]}
    return {"ai_calls": calls, "sections": sections}


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_quotes(state: CvScreenState) -> dict:
    """Keeps a quote only if those exact words are in the CV. The AI may never invent evidence."""
    texts = (_plain(state["text"]), _plain(state["clean_text"]))      # the AI saw the text without contacts
    sections = {}
    for name, part in state["sections"].items():
        proof = bool(part["quote"]) and any(_plain(part["quote"]) in text for text in texts)
        sections[name] = {**part, "quote": part["quote"] if proof else "", "proof": proof}
    return {"sections": sections}


def ats_match(state: CvScreenState) -> dict:
    """The ATS match score: how many of the job's ATS keywords the CV contains (code only, no AI).
    The keywords were made once for the job (screening_service.ats_keywords)."""
    keywords = state["job"].get("ats_keywords") or []
    if not keywords:
        return {"ats": {}}
    matched = [k for k in keywords if find_skill(k, state["profile"]["skills"], state["text"])]
    missing = [k for k in keywords if k not in matched]
    return {"ats": {"score": round(100 * len(matched) / len(keywords)), "matched": matched, "missing": missing,
                    "total": len(keywords)}}


def combine_score(state: CvScreenState) -> dict:
    return {"weighted_score": weighted_score(state["sections"], state["job"]["weights"])}


def save_result(state: CvScreenState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == state["candidate_id"])).first()
        row = row or ScreeningResult(candidate_id=state["candidate_id"], job_id=state["job_id"])
        row.result, row.reason = state["result"], state["reason"]
        row.parsed, row.matches, row.missing = state["profile"], state["matches"], state["missing"]
        row.sections, row.weighted_score = state["sections"], state["weighted_score"]
        row.ats, row.ats_score = state["ats"], (state["ats"] or {}).get("score")
        # The text this screening used (for a scanned PDF: what the AI read) and any reading problem. Saved here,
        # in the screening's own table: the candidate table keeps only what the CV collection saved.
        row.cv_text, row.text_source, row.read_problem = state["text"], state["text_source"], state["problem"]
        row.stale, row.thread_id = False, state["thread_id"]
        if row.decision:                              # screening again: the system decides again (the person can
            session.add(WorkflowRun(stage="hr_decision", subject_id=state["candidate_id"],   # change it again later)
                                    outcome=f"cleared ({row.decision} by {row.decided_by or 'a person'})", seconds=0.0))
            row.decision, row.decision_note, row.decided_by, row.decided_at = "", "", "", None
        row.model = "fake" if config.LLM_PROVIDER == "fake" else config.LLM_MODEL
        session.add(row)

        session.add(WorkflowRun(stage="cv_screening", subject_id=state["candidate_id"], outcome=state["result"],
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("screening run candidate=%s result=%s ai_calls=%d seconds=%.1f", state["candidate_id"], state["result"],
             state["ai_calls"], time.time() - state["started"])
    return {}


def hr_review(state: CvScreenState) -> dict:
    """The run pauses here. LangGraph saves it (checkpointer) and gives the question to the backend; the run
    continues when the backend resumes it with the person's answer (decide() below)."""
    answer = interrupt({"candidate_id": state["candidate_id"], "system_result": state["result"]})
    return {"decision": answer if isinstance(answer, dict) else {}}


def apply_decision(state: CvScreenState) -> dict:
    """Plain code: saves exactly what the person chose. The AI is not involved."""
    choice = state["decision"].get("decision") or ""
    with Session(engine) as session:
        row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == state["candidate_id"])).one()
        row.decision = choice if choice in ("included", "excluded") else ""
        row.decision_note = str(state["decision"].get("note") or "").strip()[:500] if row.decision else ""
        row.decided_by = str(state["decision"].get("by") or "") if row.decision else ""
        row.decided_at = datetime.now(timezone.utc) if row.decision else None
        session.add(row)
        outcome = row.decision or "undone"
        session.add(WorkflowRun(stage="hr_decision", subject_id=state["candidate_id"], outcome=outcome, seconds=0.0))
        session.commit()
    log.info("hr decision candidate=%s decision=%s", state["candidate_id"], outcome)
    return {}


# ---------- routing (Python decides which step comes next) ----------

def where_to_start(state: CvScreenState) -> str:
    return "hr_review" if state.get("review_only") else "parse_cv"


def after_validate(state: CvScreenState) -> str:
    if not state["problem"]:
        return "extract_profile" if state["english"] else "needs_review"
    is_pdf = Path(state["file_path"]).suffix.lower() == ".pdf"
    if is_pdf and state["ocr_tries"] < MAX_OCR_TRIES and Path(state["file_path"]).is_file():
        return "ocr_once"
    return "needs_review"


def after_justify(state: CvScreenState) -> str:
    return "save_result" if state["result"] == "needs_review" else "score_sections"


def after_score(state: CvScreenState) -> str:
    return "check_quotes" if state["sections"] else "save_result"   # the AI could not score: saved without scores


def after_extract(state: CvScreenState) -> str:
    if state["profile"]:
        return "match_requirements"
    return "extract_profile" if state["profile_tries"] < MAX_PROFILE_TRIES else "needs_review"


# ---------- wiring ----------

graph = StateGraph(CvScreenState)
graph.add_node("parse_cv", parse_cv)
graph.add_node("validate_extraction", validate_extraction)
graph.add_node("ocr_once", ocr_once)
graph.add_node("needs_review", needs_review)
graph.add_node("extract_profile", extract_profile)
graph.add_node("match_requirements", match_requirements)
graph.add_node("justifications", justifications)
graph.add_node("score_sections", score_sections)
graph.add_node("check_quotes", check_quotes)
graph.add_node("ats_match", ats_match)
graph.add_node("combine_score", combine_score)
graph.add_node("save_result", save_result)
graph.add_node("hr_review", hr_review)
graph.add_node("apply_decision", apply_decision)

graph.add_conditional_edges(START, where_to_start, ["parse_cv", "hr_review"])
graph.add_edge("parse_cv", "validate_extraction")
graph.add_conditional_edges("validate_extraction", after_validate, ["extract_profile", "ocr_once", "needs_review"])
graph.add_edge("ocr_once", "validate_extraction")          # the loop: the AI's text is checked like any other
graph.add_conditional_edges("extract_profile", after_extract, ["match_requirements", "extract_profile", "needs_review"])
graph.add_edge("match_requirements", "justifications")
graph.add_conditional_edges("justifications", after_justify, ["score_sections", "save_result"])
graph.add_conditional_edges("score_sections", after_score, ["check_quotes", "save_result"])
graph.add_edge("check_quotes", "ats_match")
graph.add_edge("ats_match", "combine_score")
graph.add_edge("combine_score", "save_result")
graph.add_edge("needs_review", "save_result")
graph.add_edge("save_result", "hr_review")
graph.add_edge("hr_review", "apply_decision")
graph.add_edge("apply_decision", "hr_review")              # the loop: a decision can be changed again later

cv_screening_graph = graph.compile()                       # for drawing (scripts/print_workflows.py)
_runner = None


def runner():
    """The workflow with the checkpointer, so a run can pause in hr_review and be continued later."""
    global _runner
    if _runner is None:
        _runner = graph.compile(checkpointer=checkpointer())
    return _runner


def _thread(candidate_id: int) -> str:
    return f"cv-screening-{candidate_id}-{uuid.uuid4().hex[:12]}"


def screen_cv(candidate_id: int, job_id: int, job: dict, file_path: str) -> CvScreenState:
    """Runs the workflow for one CV until it pauses in hr_review. The result is saved by save_result before that."""
    thread_id = _thread(candidate_id)
    state: CvScreenState = {"thread_id": thread_id, "review_only": False, "decision": {}, "candidate_id": candidate_id, "job_id": job_id, "job": job, "file_path": file_path,
                            "text": "", "pages": 1, "text_source": "", "problem": "", "ocr_tries": 0, "english": True,
                            "clean_text": "", "profile": {}, "profile_tries": 0, "ai_calls": 0, "matches": [], "missing": [], "sections": {}, "weighted_score": None, "ats": {},
                            "result": "", "reason": "", "error": "", "started": time.time()}
    try:
        return runner().invoke(state, {"configurable": {"thread_id": thread_id}})
    except Exception:
        log.exception("cv screening workflow could not run")
        failed = {**state, "result": "needs_review", "reason": "The screening stopped unexpectedly. Try again.",
                  "error": "the workflow stopped unexpectedly, see the backend log"}
        save_result(failed)
        return failed


def decide(candidate_id: int, job_id: int, decision: str, note: str, by: str) -> None:
    """The person's answer for the paused run of this candidate: decision is included, excluded or "" (undo).
    If no paused run is found (for example a CV screened before this step existed), a short run is started that
    goes straight to hr_review, so the decision still goes through the workflow."""
    with Session(engine) as session:
        row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).one()
        thread_id, result = row.thread_id, row.result
    graph_runner = runner()
    config = {"configurable": {"thread_id": thread_id}}
    if not thread_id or graph_runner.get_state(config).next != ("hr_review",):
        thread_id = _thread(candidate_id)
        config = {"configurable": {"thread_id": thread_id}}
        graph_runner.invoke({"thread_id": thread_id, "review_only": True, "decision": {}, "candidate_id": candidate_id,
                             "job_id": job_id, "result": result}, config)
        with Session(engine) as session:
            row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).one()
            row.thread_id = thread_id
            session.add(row)
            session.commit()
    graph_runner.invoke(Command(resume={"decision": decision, "note": note, "by": by}), config)
