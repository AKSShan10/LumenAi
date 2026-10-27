"""CV claim verification (F8): CV claims compared with what the candidate said in the interview.

Read this file from top to bottom:
    start(session, candidate)    "Check CV claims": needs the CV text and an ended interview; marks it running
    result(session, candidate)   the claims for the report page (it asks every 3 s while "running")
    resume_running()             after a restart: checks that were still running start again
    run(candidate_id)            the check: the 5 steps in order, then save (or failed)
    then the 5 steps, in the same order as run() calls them:
    Step 1  load_inputs             Python + DB  the CV text (without email and phone) and the candidate's transcript
                                                 lines of the newest ended interview, numbered, with their times
    Step 2  extract_claims          AI           up to 8 concrete claims from the CV, each with a CV quote
    Step 3  check_cv_quotes         Python       a claim stays only if its quote is really in the CV
    Step 4  compare_claims          AI           for each claim: supported | contradicted | unverified | not_discussed,
                                                 a quote from the candidate's own words, a neutral note and a follow-up
    Step 5  check_interview_quotes  Python       the quote must be in that line of the candidate (then its time is
                                                 added); without proof a claim becomes "not_discussed", so nothing is
                                                 called a contradiction without the candidate's own words; accusing
                                                 words are removed

Search for "Step 3 of 5" to jump to a step; its small helpers are right below it. A step that cannot go on
raises CheckFailed, and run() saves the reason.

Plain Python, not LangGraph: a straight line of steps (no loop, no pause, no parallel steps).
The interviewer only. Flags are prompts for follow-up questions, never accusations, scores or decisions.
"""
import logging
import re
import time
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.claims.models import ClaimCheck
from app.features.claims.schemas import ClaimCheckOut
from app.features.claims.services.claim_prompts import COMPARE_PROMPT, EXTRACT_PROMPT
from app.features.interviews.models import InterviewSession
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.graphs.cv_screening_graph import remove_contacts
from app.utils.datetime_utils import utc_now

log = logging.getLogger("claims")

MAX_CLAIMS = 8
STATUSES = ("supported", "contradicted", "unverified", "not_discussed")
# Words that would turn a follow-up prompt into an accusation; a note or question with one is replaced by neutral text
ACCUSING = re.compile(r"\b(lie[sd]?|lying|liar|false(ly)?|fake[sd]?|faked|dishonest\w*|fabricat\w*|cheat\w*|"
                      r"mislead\w*|exaggerat\w*|fraud\w*)\b", re.IGNORECASE)
NEUTRAL_NOTE = {"supported": "The interview backs this claim up.",
                "contradicted": "What was said in the interview does not seem to fit this claim.",
                "unverified": "The topic came up, but the answer did not back the claim up.",
                "not_discussed": "This claim did not come up in the interview."}


class CheckFailed(Exception):
    """A step could not go on; the message is shown on the page."""


# ---------- called by the router ----------

def _row(session: Session, candidate_id: int) -> ClaimCheck | None:
    return session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == candidate_id)).first()


def start(session: Session, candidate: Candidate) -> ClaimCheckOut:
    screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first()
    if not screening or not (screening.cv_text or "").strip():
        raise HTTPException(409, "The CV has no text yet. Screen the CV first.")
    ended = session.exec(select(InterviewSession).where(InterviewSession.candidate_id == candidate.id,
                                                        InterviewSession.status == "ended")).first()
    if not ended:
        raise HTTPException(409, "End the interview first. The CV claims are compared with what was said.")
    row = _row(session, candidate.id)
    if row and row.status == "running":
        raise HTTPException(409, "The claim check is already running. Please wait a moment.")
    row = row or ClaimCheck(candidate_id=candidate.id)
    row.status, row.error, row.updated_at = "running", "", utc_now()          # the old result stays until the new one
    session.add(row)
    session.commit()
    return result(session, candidate)


def result(session: Session, candidate: Candidate) -> ClaimCheckOut:
    row = _row(session, candidate.id)
    if not row:
        return ClaimCheckOut(candidate_id=candidate.id, status="not_started")
    return ClaimCheckOut(candidate_id=candidate.id, session_id=row.session_id, status=row.status, error=row.error or "",
                         claims=row.claims or [], updated_at=row.updated_at)


def resume_running() -> None:
    """Checks that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(ClaimCheck.candidate_id).where(ClaimCheck.status == "running")).all()
    for candidate_id in waiting:
        log.info("claim check candidate=%s resumed after a restart", candidate_id)
        run(candidate_id)


# ---------- the check: 5 steps in order, then save or failed ----------

def run(candidate_id: int) -> None:
    """Runs the check for one candidate and saves the result. The claim_check row must exist. Never raises."""
    started = time.time()
    try:
        cv_text, lines, session_id = load_inputs(candidate_id)  # Step 1
        claims = extract_claims(cv_text)                       # Step 2  → AI call
        claims = check_cv_quotes(claims, cv_text)              # Step 3
        claims = compare_claims(claims, lines)                 # Step 4  → AI call
        claims = check_interview_quotes(claims, lines)         # Step 5
        save(candidate_id, session_id, claims, started)
    except CheckFailed as problem:
        failed(candidate_id, str(problem), started)
    except Exception:
        log.exception("claim check could not run")
        failed(candidate_id, "The claim check stopped unexpectedly. Please try again.", started)


# "save": the result replaces the old one
def save(candidate_id: int, session_id: int, claims: list, started: float) -> None:
    with Session(engine) as session:
        row = session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == candidate_id)).one()
        row.status, row.error, row.claims, row.session_id = "done", "", claims, session_id
        session.add(row)
        session.add(WorkflowRun(stage="claim_check", subject_id=candidate_id, outcome="done",
                                seconds=round(time.time() - started, 2)))
        session.commit()
    log.info("claim check candidate=%s done claims=%s", candidate_id, len(claims))


# "failed": the check is marked failed with the reason, so the page can show it
def failed(candidate_id: int, error: str, started: float) -> None:
    with Session(engine) as session:
        row = session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == candidate_id)).first()
        if row:
            row.status, row.error = "failed", error
            session.add(row)
        session.add(WorkflowRun(stage="claim_check", subject_id=candidate_id, outcome="failed",
                                error=error, seconds=round(time.time() - started, 2)))
        session.commit()
    log.info("claim check candidate=%s failed: %s", candidate_id, error)


# ############################## the 5 steps ##############################


# ==================== Step 1 of 5: load_inputs ====================
# Python + DB: the CV text and the candidate's lines of the newest ended interview
def load_inputs(candidate_id: int) -> tuple[str, list, int]:
    with Session(engine) as session:
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).first()
        interview = session.exec(select(InterviewSession)
                                 .where(InterviewSession.candidate_id == candidate_id,
                                        InterviewSession.status == "ended")
                                 .order_by(InterviewSession.ended_at.desc(), InterviewSession.id.desc())).first()
        turns = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == (interview.id if interview else 0),
                                                          TranscriptTurn.speaker == "candidate")
                             .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()
    if not screening or not (screening.cv_text or "").strip():
        raise CheckFailed("The CV has no text yet. Screen the CV first.")
    if not interview or not turns:
        raise CheckFailed("No ended interview with the candidate's words was found.")
    lines = [{"n": n, "start": t.start_sec, "text": t.text} for n, t in enumerate(turns, 1)]
    return remove_contacts(screening.cv_text), lines, interview.id


# ==================== Step 2 of 5: extract_claims ====================
# AI: the CV's concrete claims, each with a CV quote
def extract_claims(cv_text: str) -> list:
    answer = llm_json(EXTRACT_PROMPT, {"cv_text": cv_text[:8000]})                # → AI call
    if not isinstance(answer, dict):
        raise CheckFailed(f"The AI did not answer ({last_error()}). Please try again.")
    claims = [{"claim": str(c.get("claim") or "").strip()[:300], "cv_quote": str(c.get("cv_quote") or "").strip()[:300]}
              for c in answer.get("claims") or [] if isinstance(c, dict)]
    return [c for c in claims if c["claim"]]


# ==================== Step 3 of 5: check_cv_quotes ====================
# Python: only claims whose words are really in the CV (_found is also used in step 5)
def check_cv_quotes(claims: list, cv_text: str) -> list:
    return [c for c in claims if _found(c["cv_quote"], cv_text)][:MAX_CLAIMS]


# One word proves nothing: a quote needs at least two words and must be found in the text
def _found(quote: str, text: str) -> bool:
    wanted = _plain(quote)
    return len(wanted.split()) >= 2 and wanted in _plain(text)


# Lower case, letters and digits only, so "FastAPI," matches "fastapi"
def _plain(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


# ==================== Step 4 of 5: compare_claims ====================
# AI: every claim compared with the candidate's interview lines
def compare_claims(claims: list, lines: list) -> list:
    if not claims:
        return []                                                                 # nothing to compare
    facts = {"claims": [{"n": n, "claim": c["claim"]} for n, c in enumerate(claims, 1)],
             "lines": [{"n": line["n"], "text": line["text"]} for line in lines]}
    answer = llm_json(COMPARE_PROMPT, facts)                                      # → AI call
    if not isinstance(answer, dict):
        raise CheckFailed(f"The AI did not answer ({last_error()}). Please try again.")
    found = {_number(item.get("n")): item for item in answer.get("claims") or [] if isinstance(item, dict)}
    return [{**c, "answer": found.get(n, {})} for n, c in enumerate(claims, 1)]


def _number(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ==================== Step 5 of 5: check_interview_quotes ====================
# Python: proof from the candidate's own words, or "not_discussed"; neutral wording
def check_interview_quotes(claims: list, lines: list) -> list:
    by_number = {line["n"]: line for line in lines}
    items = []
    for claim in claims:
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
    return sorted(items, key=lambda i: order[i["status"]])                  # what needs a follow-up first


# A note or question without accusing words (else the neutral text for that status)
def _neutral(text: str, fallback: str) -> str:
    text = str(text or "").strip()[:300]
    return fallback if not text or ACCUSING.search(text) else text
