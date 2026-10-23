"""CV claim verification (F8): start it, read it, run it in the background.

    start(session, candidate)    "Check CV claims": needs the CV text and an ended interview; marks it running
    run(candidate_id)            runs the workflow (graphs/claim_check_graph.py); called as a background task
    result(session, candidate)   the claims for the report page (it asks every 3 s while "running")
    resume_running()             after a restart: checks that were still running start again

The interviewer only. Flags are prompts for follow-up questions, never accusations, scores or decisions.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.claims.models import ClaimCheck
from app.features.claims.schemas import ClaimCheckOut
from app.features.interviews.models import InterviewSession
from app.features.screening.models import ScreeningResult
from app.graphs.claim_check_graph import check_claims
from app.utils.datetime_utils import utc_now

log = logging.getLogger("claims")


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


def run(candidate_id: int) -> None:
    check_claims(candidate_id)                        # → the LangGraph workflow; it saves the result itself


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
