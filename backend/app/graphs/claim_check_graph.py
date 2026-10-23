"""The CV claim verification workflow (F8): CV claims compared with what the candidate said in the interview.

    START -> load_inputs -> extract_claims -> check_cv_quotes -> compare_claims -> check_interview_quotes -> save -> END
    any error -> failed -> END

    load_inputs             Python + DB  the CV text (without email and phone) and the candidate's transcript lines of
                                         the newest ended interview, numbered, with their times
    extract_claims          AI           up to 8 concrete claims from the CV, each with a CV quote
    check_cv_quotes         Python       a claim stays only if its quote is really in the CV
    compare_claims          AI           for each claim: supported | contradicted | unverified | not_discussed,
                                         a quote from the candidate's own words, a neutral note and a follow-up question
    check_interview_quotes  Python       the quote must be in that line of the candidate (then its time is added);
                                         without proof a claim becomes "not_discussed", so nothing is called a
                                         contradiction without the candidate's own words; accusing words are removed
    save / failed           Python + DB  the result (or the reason) and one workflow_run row

The flags are prompts for the interviewer's follow-up questions: never an accusation, never a score, never a decision.
"""
import logging
import re
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.claims.models import ClaimCheck
from app.features.interviews.models import InterviewSession
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.graphs.claim_check_prompts import COMPARE_PROMPT, EXTRACT_PROMPT
from app.graphs.cv_screening_graph import remove_contacts

log = logging.getLogger("claim_check_graph")

MAX_CLAIMS = 8
STATUSES = ("supported", "contradicted", "unverified", "not_discussed")
# Words that would turn a follow-up prompt into an accusation; a note or question with one is replaced by neutral text
ACCUSING = re.compile(r"\b(lie[sd]?|lying|liar|false(ly)?|fake[sd]?|faked|dishonest\w*|fabricat\w*|cheat\w*|"
                      r"mislead\w*|exaggerat\w*|fraud\w*)\b", re.IGNORECASE)
NEUTRAL_NOTE = {"supported": "The interview backs this claim up.",
                "contradicted": "What was said in the interview does not seem to fit this claim.",
                "unverified": "The topic came up, but the answer did not back the claim up.",
                "not_discussed": "This claim did not come up in the interview."}


class ClaimState(TypedDict):
    candidate_id: int
    session_id: Optional[int]
    cv_text: str
    lines: list                 # the candidate's transcript lines: [{"n", "start", "text"}]
    claims: list                # [{"claim", "cv_quote"}] and, after compare, the full items
    error: str
    started: float


# Lower case, letters and digits only, so "FastAPI," matches "fastapi"
def _plain(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


# One word proves nothing: a quote needs at least two words and must be found in the text
def _found(quote: str, text: str) -> bool:
    wanted = _plain(quote)
    return len(wanted.split()) >= 2 and wanted in _plain(text)


def _number(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# A note or question without accusing words (else the neutral text for that status)
def _neutral(text: str, fallback: str) -> str:
    text = str(text or "").strip()[:300]
    return fallback if not text or ACCUSING.search(text) else text


# ---------- nodes ----------

# Workflow step "load_inputs": the CV text and the candidate's lines of the newest ended interview
def load_inputs(state: ClaimState) -> dict:
    with Session(engine) as session:
        screening = session.exec(select(ScreeningResult)
                                 .where(ScreeningResult.candidate_id == state["candidate_id"])).first()
        interview = session.exec(select(InterviewSession)
                                 .where(InterviewSession.candidate_id == state["candidate_id"],
                                        InterviewSession.status == "ended")
                                 .order_by(InterviewSession.ended_at.desc(), InterviewSession.id.desc())).first()
        turns = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == (interview.id if interview else 0),
                                                          TranscriptTurn.speaker == "candidate")
                             .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()
    if not screening or not (screening.cv_text or "").strip():
        return {"error": "The CV has no text yet. Screen the CV first."}
    if not interview or not turns:
        return {"error": "No ended interview with the candidate's words was found."}
    lines = [{"n": n, "start": t.start_sec, "text": t.text} for n, t in enumerate(turns, 1)]
    return {"cv_text": remove_contacts(screening.cv_text), "lines": lines, "session_id": interview.id}


# Workflow step "extract_claims": the AI lists the CV's concrete claims
def extract_claims(state: ClaimState) -> dict:
    answer = llm_json(EXTRACT_PROMPT, {"cv_text": state["cv_text"][:8000]})       # → AI call
    if not isinstance(answer, dict):
        return {"error": f"The AI did not answer ({last_error()}). Please try again."}
    claims = [{"claim": str(c.get("claim") or "").strip()[:300], "cv_quote": str(c.get("cv_quote") or "").strip()[:300]}
              for c in answer.get("claims") or [] if isinstance(c, dict)]
    return {"claims": [c for c in claims if c["claim"]]}


# Workflow step "check_cv_quotes": only claims whose words are really in the CV
def check_cv_quotes(state: ClaimState) -> dict:
    return {"claims": [c for c in state["claims"] if _found(c["cv_quote"], state["cv_text"])][:MAX_CLAIMS]}


# Workflow step "compare_claims": the AI compares every claim with the candidate's interview lines
def compare_claims(state: ClaimState) -> dict:
    if not state["claims"]:
        return {}                                                                 # nothing to compare
    facts = {"claims": [{"n": n, "claim": c["claim"]} for n, c in enumerate(state["claims"], 1)],
             "lines": [{"n": line["n"], "text": line["text"]} for line in state["lines"]]}
    answer = llm_json(COMPARE_PROMPT, facts)                                      # → AI call
    if not isinstance(answer, dict):
        return {"error": f"The AI did not answer ({last_error()}). Please try again."}
    found = {_number(item.get("n")): item for item in answer.get("claims") or [] if isinstance(item, dict)}
    return {"claims": [{**c, "answer": found.get(n, {})} for n, c in enumerate(state["claims"], 1)]}


# Workflow step "check_interview_quotes": proof from the candidate's own words, or "not_discussed"; neutral wording
def check_interview_quotes(state: ClaimState) -> dict:
    by_number = {line["n"]: line for line in state["lines"]}
    items = []
    for claim in state["claims"]:
        answer = claim.get("answer") or {}
        status = str(answer.get("status") or "").strip().lower()
        status = status if status in STATUSES else "not_discussed"
        quote = str(answer.get("interview_quote") or "").strip()[:300]
        line = by_number.get(_number(answer.get("line")))
        if status != "not_discussed" and not (line and _found(quote, line["text"])):
            status, quote, line = "not_discussed", "", None                  # no proof: never called a contradiction
        if status == "not_discussed":
            quote, line = "", None
        items.append({"claim": claim["claim"], "cv_quote": claim["cv_quote"], "status": status,
                      "interview_quote": quote, "time": line["start"] if line else None,
                      "note": _neutral(answer.get("note"), NEUTRAL_NOTE[status]),
                      "follow_up": "" if status == "supported" else _neutral(
                          answer.get("follow_up"), f"Could you tell me more about this: {claim['claim']}"),
                      })
    order = {s: i for i, s in enumerate(("contradicted", "unverified", "not_discussed", "supported"))}
    return {"claims": sorted(items, key=lambda i: order[i["status"]])}      # what needs a follow-up first


# Workflow step "save": the result replaces the old one
def save(state: ClaimState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == state["candidate_id"])).one()
        row.status, row.error, row.claims, row.session_id = "done", "", state["claims"], state["session_id"]
        session.add(row)
        session.add(WorkflowRun(stage="claim_check", subject_id=state["candidate_id"], outcome="done",
                                seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("claim check candidate=%s done claims=%s", state["candidate_id"], len(state["claims"]))
    return {}


# Workflow step "failed": the check is marked failed with the reason, so the page can show it
def failed(state: ClaimState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == state["candidate_id"])).first()
        if row:
            row.status, row.error = "failed", state["error"]
            session.add(row)
        session.add(WorkflowRun(stage="claim_check", subject_id=state["candidate_id"], outcome="failed",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("claim check candidate=%s failed: %s", state["candidate_id"], state["error"])
    return {}


# After a step: go on, or to "failed" when the step set an error
def go_on(state: ClaimState) -> str:
    return "failed" if state["error"] else "go"


graph = StateGraph(ClaimState)
graph.add_node("load_inputs", load_inputs)
graph.add_node("extract_claims", extract_claims)
graph.add_node("check_cv_quotes", check_cv_quotes)
graph.add_node("compare_claims", compare_claims)
graph.add_node("check_interview_quotes", check_interview_quotes)
graph.add_node("save", save)
graph.add_node("failed", failed)

graph.add_edge(START, "load_inputs")
graph.add_conditional_edges("load_inputs", go_on, {"go": "extract_claims", "failed": "failed"})
graph.add_conditional_edges("extract_claims", go_on, {"go": "check_cv_quotes", "failed": "failed"})
graph.add_edge("check_cv_quotes", "compare_claims")
graph.add_conditional_edges("compare_claims", go_on, {"go": "check_interview_quotes", "failed": "failed"})
graph.add_edge("check_interview_quotes", "save")
graph.add_edge("save", END)
graph.add_edge("failed", END)

claim_check_graph = graph.compile()


def check_claims(candidate_id: int) -> ClaimState:
    """Runs the workflow for one candidate. The claim_check row must exist (status running). Never raises."""
    state: ClaimState = {"candidate_id": candidate_id, "session_id": None, "cv_text": "", "lines": [], "claims": [],
                         "error": "", "started": time.time()}
    try:
        return claim_check_graph.invoke(state)
    except Exception:
        log.exception("claim check workflow could not run")
        stopped = {**state, "error": "The claim check stopped unexpectedly. Please try again."}
        failed(stopped)
        return stopped
