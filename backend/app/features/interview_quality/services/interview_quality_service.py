"""Interview quality assessment (F10): start it, read it, run it in the background.

    start(session, interview)    "Check interview quality": needs the finished Q&A analysis; marks it running
    run(session_id)              runs the workflow (graphs/interview_quality_graph.py); called as a background task
    result(session, interview)   the result for the analysis page (it asks every 3 s while "running")
    resume_running()             after a restart: checks that were still running start again

The interviewer only. It judges the process, never a person, and never changes a score or a decision.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.database import engine
from app.features.interview_quality.models import InterviewQuality
from app.features.interview_quality.schemas import InterviewQualityOut
from app.features.interviews.models import InterviewSession
from app.features.qa_analysis.models import QaAnalysis
from app.graphs.interview_quality_graph import assess_interview
from app.utils.datetime_utils import utc_now

log = logging.getLogger("interview_quality")


def _row(session: Session, session_id: int) -> InterviewQuality | None:
    """The interview_quality row of one interview, or None."""
    return session.exec(select(InterviewQuality).where(InterviewQuality.session_id == session_id)).first()


def start(session: Session, interview: InterviewSession) -> InterviewQualityOut:
    """"Check interview quality": needs the finished Q&A analysis; marks the check running."""
    analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == interview.id)).first()
    if not analysis or analysis.status != "done":
        raise HTTPException(409, "Analyse the answers first. The interview quality uses the Q&A analysis.")
    row = _row(session, interview.id)
    if row and row.status == "running":
        raise HTTPException(409, "The interview quality check is already running. Please wait a moment.")
    row = row or InterviewQuality(session_id=interview.id)
    row.status, row.error, row.updated_at = "running", "", utc_now()          # the old result stays until the new one
    session.add(row)
    session.commit()
    return result(session, interview)


def run(session_id: int) -> None:
    """Runs the workflow (graphs/interview_quality_graph.py); called as a background task."""
    assess_interview(session_id)                      # → the LangGraph workflow; it saves the result itself


def result(session: Session, interview: InterviewSession) -> InterviewQualityOut:
    """The result for the analysis page (status not_started when nobody started it)."""
    row = _row(session, interview.id)
    if not row:
        return InterviewQualityOut(session_id=interview.id, status="not_started")
    return InterviewQualityOut(**row.model_dump(exclude={"id"}))


def resume_running() -> None:
    """Checks that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(InterviewQuality.session_id).where(InterviewQuality.status == "running")).all()
    for session_id in waiting:
        log.info("interview quality session=%s resumed after a restart", session_id)
        run(session_id)
