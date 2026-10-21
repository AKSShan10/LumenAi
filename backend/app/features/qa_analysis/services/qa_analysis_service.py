"""Q&A analysis (F5): start it, read it, run it in the background.

    start(session, interview)   "Analyse answers": marks the analysis running and clears the old result
    run(session_id)             runs the workflow (graphs/qa_analysis_graph.py); called as a background task
    result(session, interview)  the analysis with every question and answer, for the page (it asks every 3 s)
    resume_running()            after a restart: analyses that were still running start again

The interviewer only. The AI suggests the grades, code checks them, and a person decides.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, delete, select

from app.core.database import engine
from app.features.interviews.models import InterviewSession
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.qa_analysis.schemas import QaAnalysisOut, QaItemOut
from app.graphs.qa_analysis_graph import analyse_interview

log = logging.getLogger("qa_analysis")


def start(session: Session, interview: InterviewSession) -> QaAnalysisOut:
    """Marks the analysis running (a new one, or again); the router then runs it in the background."""
    if interview.status != "ended":
        raise HTTPException(409, "End the interview first. The answers are analysed after the call.")
    row = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == interview.id)).first()
    if row and row.status == "running":
        raise HTTPException(409, "The analysis is already running. Please wait a moment.")
    row = row or QaAnalysis(session_id=interview.id)
    row.status, row.error, row.interview_score, row.covered, row.uncovered = "running", "", None, [], []
    session.add(row)
    session.exec(delete(QaItem).where(QaItem.session_id == interview.id))    # the old result is replaced
    session.commit()
    return result(session, interview)


def run(session_id: int) -> None:
    """The work itself (about 6 AI calls). Runs after the answer was sent, so the page does not wait."""
    analyse_interview(session_id)                     # → the LangGraph workflow; it saves the result itself


def result(session: Session, interview: InterviewSession) -> QaAnalysisOut:
    """The analysis of this interview; status "not_started" if nobody clicked "Analyse answers" yet."""
    row = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == interview.id)).first()
    if not row:
        return QaAnalysisOut(session_id=interview.id, status="not_started")
    items = session.exec(select(QaItem).where(QaItem.session_id == interview.id).order_by(QaItem.position)).all()
    return QaAnalysisOut(session_id=interview.id, status=row.status, error=row.error or "",
                         interview_score=row.interview_score, covered=row.covered or [],
                         uncovered=row.uncovered or [], created_at=row.created_at,
                         # follow_up is empty (NULL) for answers analysed before that column existed (migration 0030)
                         items=[QaItemOut(**{**item.model_dump(), "follow_up": item.follow_up or ""})
                                for item in items])


def resume_running() -> None:
    """Analyses that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(QaAnalysis.session_id).where(QaAnalysis.status == "running")).all()
    for session_id in waiting:
        log.info("qa analysis session=%s resumed after a restart", session_id)
        run(session_id)
