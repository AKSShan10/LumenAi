"""Interview quality assessment (F10), interviewer only. The work is in services/interview_quality_service.py and
graphs/interview_quality_graph.py.

  POST /api/sessions/{id}/quality   "Check interview quality": answers 202 at once, the work runs in the background
  GET  /api/sessions/{id}/quality   the result and its status; the page asks every 3 seconds while "running"
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.interview_quality.schemas import InterviewQualityOut
from app.features.interview_quality.services import interview_quality_service
from app.features.interviews.routers.interview_router import get_interview_or_404

router = APIRouter(prefix="/api/sessions", tags=["Interview quality"], dependencies=[Depends(require_interviewer)])


@router.post("/{session_id}/quality", response_model=InterviewQualityOut, status_code=202)
def start_quality_check(session_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    started = interview_quality_service.start(session, get_interview_or_404(session, session_id))
    background.add_task(interview_quality_service.run, session_id)    # → runs after the answer is sent
    return started


@router.get("/{session_id}/quality", response_model=InterviewQualityOut)
def get_quality(session_id: int, session: Session = Depends(get_session)):
    return interview_quality_service.result(session, get_interview_or_404(session, session_id))
