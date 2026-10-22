"""The assessment workflow (F6): the CV screening and the interview analysis become one report per candidate.

    START -> load_all_results
          -> [analyze_strengths | analyze_weaknesses | evidence_gaps | recommended_areas]   (parallel)
          -> merge_assessment -> validate_traceability --all proven--> generate_report -> save -> END
                                      |  ^
                       quote not found |  | (at most MAX_REPAIRS times; after that, unproven items are removed)
                                      v  |
                                repair_assessment
    any error -> failed -> END

    load_all_results       Python + database: the job, the CV (text, matches, CV score), the interview analysis
    analyze_strengths      AI: 2-5 strengths, each with a quote from the CV or the interview
    analyze_weaknesses     AI: 2-5 weaknesses, each with a quote
    evidence_gaps          Python: job requirements with no proof in the CV or the interview
    recommended_areas      AI: 2-4 areas to explore in a next interview or reference check
    merge_assessment       Python: checks that the three AI steps answered
    validate_traceability  Python: is every quote really in the CV or the candidate's answers?
    repair_assessment      AI: fixes the items whose quote was not found
    generate_report        Python: overall score (CV x 40 % + interview x 60 %); AI: the summary, written last
    save / failed          Python + database: the report (or the reason it failed) and one workflow_run row

The AI suggests, code checks. The AI never decides: the interviewer records hire, hold or reject.
About 4-6 AI calls per candidate.
"""
import logging
import re
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.core import config
from app.core.database import engine
from app.features.assessments.models import Assessment
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.graphs.assessment_prompts import (
    AREAS_PROMPT, REPAIR_PROMPT, STRENGTHS_PROMPT, SUMMARY_PROMPT, WEAKNESSES_PROMPT)
from app.graphs.cv_screening_graph import remove_contacts

log = logging.getLogger("assessment_graph")

MAX_REPAIRS = 2                  # how often items without proof go back to the AI
MAX_ITEMS = 5                    # the most strengths (and weaknesses) kept
PARALLEL_STEPS = ["analyze_strengths", "analyze_weaknesses", "evidence_gaps", "recommended_areas"]


class AssessmentState(TypedDict):
    candidate_id: int
    job_id: int
    session_id: Optional[int]          # the interview whose analysis is used
    facts: dict                        # what every AI call gets: job, CV text, CV matches, graded answers, scores
    cv_text: str                       # the CV (without email and phone), for the quote check
    answers_text: str                  # everything the candidate said, for the quote check
    requirements: list                 # the job's required and preferred skills
    cv_proof: list                     # requirements the CV met or partly met
    covered: list                      # requirements the interview showed (from the Q&A analysis)
    cv_score: Optional[float]
    interview_score: Optional[float]
    # Each parallel step writes only its own key, so the four can run at the same time. None = the AI failed.
    strengths: Optional[list]
    weaknesses: Optional[list]
    gaps: list
    areas: Optional[list]
    problems: list                     # items whose quote was not found
    repair_rounds: int
    summary: str
    cv_weight: int                     # the CV part of the overall score in %, read from the job when it is used
    overall_score: Optional[float]
    error: str                         # set when a step failed: the workflow goes to "failed"
    started: float


# ---------- helpers ----------

# Lower case, letters and digits only, so "FastAPI, mostly!" matches "fastapi mostly"
def _plain(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


# Where a quote really is: "CV", "Interview", or "" when it is in neither (one word proves nothing)
def _found_in(quote: str, state: AssessmentState) -> str:
    wanted = _plain(quote)
    if len(wanted.split()) < 2:
        return ""
    if wanted in _plain(state["cv_text"]):
        return "CV"
    if wanted in _plain(state["answers_text"]):
        return "Interview"
    return ""


# Cleans a list of strengths or weaknesses from the AI: text and quote only, trimmed, at most MAX_ITEMS
def _items(answer, key: str) -> Optional[list]:
    if not isinstance(answer, dict):
        return None                                    # the AI did not answer
    items = []
    for item in answer.get(key) or []:
        if isinstance(item, dict) and str(item.get("text") or "").strip():
            items.append({"text": str(item["text"]).strip()[:300], "quote": str(item.get("quote") or "").strip()[:300],
                          "source": str(item.get("source") or "").strip()[:20]})
    return items[:MAX_ITEMS]


# Job requirements with no proof: not met in the CV and not shown in the interview (code, not AI)
def _gaps(state: AssessmentState) -> list:
    return [r for r in state["requirements"] if r not in state["cv_proof"] and r not in state["covered"]]


# The CV part of the overall score for a job, in %: the job's own setting, or ASSESSMENT_CV_WEIGHT (40) if not set
def job_cv_weight(job: Optional[Job]) -> int:
    if job and job.assessment_cv_weight is not None:
        return job.assessment_cv_weight
    return config.ASSESSMENT_CV_WEIGHT


# Overall score = CV score x weight % + interview score x (100 - weight) %  (also used when the weight is changed)
def overall_score(cv_score: float, interview_score: float, cv_weight: int) -> float:
    return round(cv_score * cv_weight / 100 + interview_score * (100 - cv_weight) / 100, 1)


# ---------- nodes ----------

# Workflow step "load_all_results": the job, the CV screening and the newest finished interview analysis
def load_all_results(state: AssessmentState) -> dict:
    with Session(engine) as session:
        candidate = session.get(Candidate, state["candidate_id"])
        job = session.get(Job, candidate.job_id) if candidate else None
        screening = session.exec(select(ScreeningResult)
                                 .where(ScreeningResult.candidate_id == state["candidate_id"])).first()
        interview_ids = session.exec(select(InterviewSession.id)
                                     .where(InterviewSession.candidate_id == state["candidate_id"])).all()
        analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id.in_(interview_ids or [0]),
                                                         QaAnalysis.status == "done")
                                .order_by(QaAnalysis.session_id.desc())).first()
        session_id = analysis.session_id if analysis else 0
        items = session.exec(select(QaItem).where(QaItem.session_id == session_id, QaItem.job_related.is_(True))
                             .order_by(QaItem.position)).all()
        said = session.exec(select(TranscriptTurn.text).where(TranscriptTurn.session_id == session_id,
                                                              TranscriptTurn.speaker == "candidate")).all()
    if not job:
        return {"error": "The candidate or the job was not found."}
    if not screening or screening.weighted_score is None:
        return {"error": "The CV has no score yet. Screen the CV first."}
    if not analysis:
        return {"error": "Analyse the interview answers first (Interviews page)."}
    if analysis.interview_score is None:
        return {"error": "The interview analysis has no graded answers, so there is no interview score."}

    cv_text = remove_contacts(screening.cv_text or "")         # the AI never sees email or phone
    matches = [m for m in (screening.matches or []) if isinstance(m, dict)]
    requirements = list(dict.fromkeys((job.required_skills or []) + (job.preferred_skills or [])))
    answers = [{"question": i.question, "answer": i.answer, "score": i.score, "reasons": i.reasons} for i in items]
    facts = {"job": {"title": job.title, "required_skills": job.required_skills or [],
                     "preferred_skills": job.preferred_skills or [], "min_years": job.min_years,
                     "qualifications": job.qualifications},
             "cv_text": cv_text[:8000],
             "requirement_matches": [{"requirement": m.get("requirement"), "kind": m.get("kind"),
                                      "status": m.get("status"), "how": m.get("how")} for m in matches],
             "answers": answers,
             "cv_score": screening.weighted_score, "interview_score": analysis.interview_score}
    return {"job_id": job.id, "session_id": analysis.session_id, "facts": facts, "cv_text": cv_text,
            "answers_text": " ".join(list(said) + [i.answer for i in items]),
            "requirements": requirements,
            "cv_proof": [m.get("requirement") for m in matches if m.get("status") in ("met", "partial")],
            "covered": analysis.covered or [], "cv_score": screening.weighted_score,
            "interview_score": analysis.interview_score}


# Workflow steps run at the same time: strengths, weaknesses (AI), evidence gaps (code), areas to explore (AI)
def analyze_strengths(state: AssessmentState) -> dict:
    return {"strengths": _items(llm_json(STRENGTHS_PROMPT, state["facts"]), "strengths")}     # → AI call


def analyze_weaknesses(state: AssessmentState) -> dict:
    return {"weaknesses": _items(llm_json(WEAKNESSES_PROMPT, state["facts"]), "weaknesses")}  # → AI call


def evidence_gaps(state: AssessmentState) -> dict:
    return {"gaps": _gaps(state)}


def recommended_areas(state: AssessmentState) -> dict:
    answer = llm_json(AREAS_PROMPT, {**state["facts"], "evidence_gaps": _gaps(state)})       # → AI call
    if not isinstance(answer, dict):
        return {"areas": None}
    areas = [{"area": str(a.get("area") or "").strip()[:120], "why": str(a.get("why") or "").strip()[:300]}
             for a in answer.get("areas") or [] if isinstance(a, dict) and str(a.get("area") or "").strip()]
    return {"areas": areas[:4]}


# Workflow step "merge_assessment": waits for the four parallel steps; stops if an AI step did not answer
def merge_assessment(state: AssessmentState) -> dict:
    if state["strengths"] is None or state["weaknesses"] is None or state["areas"] is None:
        return {"error": f"The AI did not answer ({last_error()}). Please try again."}
    return {}


# Workflow step "validate_traceability": every strength and weakness needs a quote that is really in the CV or
# the candidate's answers. Code also writes where the quote was found (the AI's "source" is not trusted).
def validate_traceability(state: AssessmentState) -> dict:
    problems, strengths, weaknesses = [], [], []
    for key, checked in (("strengths", strengths), ("weaknesses", weaknesses)):
        for item in state[key]:
            source = _found_in(item["quote"], state)
            checked.append({**item, "source": source or item["source"]})
            if not source:
                problems.append({"list": key, "text": item["text"], "quote": item["quote"],
                                 "problem": "this quote is not in the CV text or the candidate's answers"})
    return {"strengths": strengths, "weaknesses": weaknesses, "problems": problems}


# Workflow step "repair_assessment": the AI gets the items without proof and fixes or drops them
def repair_assessment(state: AssessmentState) -> dict:
    answer = llm_json(REPAIR_PROMPT, {**state["facts"], "strengths": state["strengths"],
                                      "weaknesses": state["weaknesses"], "problems": state["problems"]})  # → AI call
    fixed = {"repair_rounds": state["repair_rounds"] + 1}
    strengths, weaknesses = _items(answer, "strengths"), _items(answer, "weaknesses")
    if strengths is not None and weaknesses is not None:     # no answer: the old lists are checked again
        fixed.update(strengths=strengths, weaknesses=weaknesses)
    return fixed


# Workflow step "generate_report": only proven items stay; overall score by code; the AI writes the summary last
def generate_report(state: AssessmentState) -> dict:
    strengths = [i for i in state["strengths"] if _found_in(i["quote"], state)]       # unproven items are removed
    weaknesses = [i for i in state["weaknesses"] if _found_in(i["quote"], state)]
    with Session(engine) as session:                  # read now, so a weight changed meanwhile is used
        weight = job_cv_weight(session.get(Job, state["job_id"]))
    overall = overall_score(state["cv_score"], state["interview_score"], weight)
    answer = llm_json(SUMMARY_PROMPT, {"job_title": state["facts"]["job"]["title"], "strengths": strengths,
                                       "weaknesses": weaknesses, "evidence_gaps": state["gaps"],
                                       "cv_score": state["cv_score"], "interview_score": state["interview_score"],
                                       "overall_score": overall})                  # → AI call
    summary = str(answer.get("summary") or "").strip() if isinstance(answer, dict) else ""
    if not summary:
        return {"error": f"The AI did not write the summary ({last_error()}). Please try again."}
    return {"strengths": strengths, "weaknesses": weaknesses, "overall_score": overall, "cv_weight": weight,
            "summary": summary[:2000]}


# Workflow step "save": the report replaces the old one; the person's decision is kept
def save(state: AssessmentState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(Assessment).where(Assessment.candidate_id == state["candidate_id"])).one()
        row.status, row.error, row.session_id = "done", "", state["session_id"]
        row.cv_score, row.interview_score = state["cv_score"], state["interview_score"]
        row.overall_score, row.cv_weight = state["overall_score"], state["cv_weight"]
        row.summary, row.repair_rounds = state["summary"], state["repair_rounds"]
        row.strengths, row.weaknesses = state["strengths"], state["weaknesses"]
        row.evidence_gaps, row.recommended_areas = state["gaps"], state["areas"]
        session.add(row)
        session.add(WorkflowRun(stage="post_interview", subject_id=state["candidate_id"], outcome="done",
                                seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("assessment candidate=%s done overall=%s repairs=%s", state["candidate_id"], state["overall_score"],
             state["repair_rounds"])
    return {}


# Workflow step "failed": the assessment is marked failed with the reason, so the page can show it
def failed(state: AssessmentState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(Assessment).where(Assessment.candidate_id == state["candidate_id"])).first()
        if row:
            row.status, row.error = "failed", state["error"]
            session.add(row)
        session.add(WorkflowRun(stage="post_interview", subject_id=state["candidate_id"], outcome="failed",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("assessment candidate=%s failed: %s", state["candidate_id"], state["error"])
    return {}


# ---------- routing ----------

# After a step: go on, or to "failed" when the step set an error
def go_on(state: AssessmentState) -> str:
    return "failed" if state["error"] else "go"


# After load_all_results: the four parallel steps, or "failed"
def after_load(state: AssessmentState):
    return "failed" if state["error"] else PARALLEL_STEPS


# After validate_traceability: all proven → report; otherwise repair (at most MAX_REPAIRS times), then report
def after_validate(state: AssessmentState) -> str:
    if state["problems"] and state["repair_rounds"] < MAX_REPAIRS:
        return "repair_assessment"
    return "generate_report"


# ---------- wiring ----------

graph = StateGraph(AssessmentState)
graph.add_node("load_all_results", load_all_results)
graph.add_node("analyze_strengths", analyze_strengths)
graph.add_node("analyze_weaknesses", analyze_weaknesses)
graph.add_node("evidence_gaps", evidence_gaps)
graph.add_node("recommended_areas", recommended_areas)
graph.add_node("merge_assessment", merge_assessment)
graph.add_node("validate_traceability", validate_traceability)
graph.add_node("repair_assessment", repair_assessment)
graph.add_node("generate_report", generate_report)
graph.add_node("save", save)
graph.add_node("failed", failed)

graph.add_edge(START, "load_all_results")
graph.add_conditional_edges("load_all_results", after_load, PARALLEL_STEPS + ["failed"])
graph.add_edge(PARALLEL_STEPS, "merge_assessment")         # waits until all four have finished
graph.add_conditional_edges("merge_assessment", go_on, {"go": "validate_traceability", "failed": "failed"})
graph.add_conditional_edges("validate_traceability", after_validate, ["repair_assessment", "generate_report"])
graph.add_edge("repair_assessment", "validate_traceability")  # the loop: repaired items are checked again
graph.add_conditional_edges("generate_report", go_on, {"go": "save", "failed": "failed"})
graph.add_edge("save", END)
graph.add_edge("failed", END)

assessment_graph = graph.compile()


def assess_candidate(candidate_id: int) -> AssessmentState:
    """Runs the workflow for one candidate. The assessment row must exist (status running). Never raises."""
    state: AssessmentState = {"candidate_id": candidate_id, "job_id": 0, "session_id": None, "facts": {},
                              "cv_text": "", "answers_text": "", "requirements": [], "cv_proof": [], "covered": [],
                              "cv_score": None, "interview_score": None, "strengths": [], "weaknesses": [],
                              "gaps": [], "areas": [], "problems": [], "repair_rounds": 0, "summary": "", "cv_weight": 0,
                              "overall_score": None, "error": "", "started": time.time()}
    try:
        return assessment_graph.invoke(state)
    except Exception:
        log.exception("assessment workflow could not run")
        stopped = {**state, "error": "The assessment stopped unexpectedly. Please try again."}
        failed(stopped)
        return stopped
