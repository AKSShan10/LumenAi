"""Q&A analysis of an interview (interviewer only, login needed; the candidate never reaches it).

  POST /api/sessions/{id}/analysis   "Analyse answers": answers 202 at once, the work runs in the background
  GET  /api/sessions/{id}/analysis   the result; the page asks every 3 seconds while it is "running"

The routes only check the request; the work is in qa_analysis_service.py and graphs/qa_analysis_graph.py.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.interviews.routers.interview_router import get_interview_or_404
from app.features.qa_analysis.schemas import QaAnalysisOut
from app.features.qa_analysis.services import qa_analysis_service

router = APIRouter(prefix="/api/sessions", tags=["Q&A analysis"], dependencies=[Depends(require_interviewer)])


@router.post("/{session_id}/analysis", response_model=QaAnalysisOut, status_code=202)
def start_analysis(session_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    """Starts the analysis of an ended interview. The answer comes at once with status "running"."""
    started = qa_analysis_service.start(session, get_interview_or_404(session, session_id))
    background.add_task(qa_analysis_service.run, session_id)    # → runs after the answer is sent
    return started


@router.get("/{session_id}/analysis", response_model=QaAnalysisOut)
def get_analysis(session_id: int, session: Session = Depends(get_session)):
    """The analysis: status, interview score, covered / uncovered requirements and every question and answer."""
    return qa_analysis_service.result(session, get_interview_or_404(session, session_id))
