"""The AI helper in the interviewer's call (interviewer only, login needed; the candidate never reaches it).

  GET  /api/sessions/{id}/helper             everything asked and answered for this interview (the tab opens)
  POST /api/sessions/{id}/helper/questions   {topic}: up to 8 suggested questions with model answers
  POST /api/sessions/{id}/helper/chat        {text}: ask the helper; returns your message and its answer

The routes only check the request; the work is in helper_service.py.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.interview_helper.schemas import HelperChatIn, HelperMessageOut, QuestionsIn
from app.features.interview_helper.services import helper_service
from app.features.interviews.routers.interview_router import get_interview_or_404

router = APIRouter(prefix="/api/sessions", tags=["Interview helper"], dependencies=[Depends(require_interviewer)])


@router.get("/{session_id}/helper", response_model=list[HelperMessageOut])
def helper_history(session_id: int, session: Session = Depends(get_session)):
    """Every question list and chat message of this interview, oldest first."""
    return helper_service.history(session, get_interview_or_404(session, session_id))


@router.post("/{session_id}/helper/questions", response_model=HelperMessageOut)
def suggest_questions(session_id: int, body: QuestionsIn, session: Session = Depends(get_session)):
    """"Suggest questions": the AI suggests up to 8, code checks them, the list is saved."""
    return helper_service.suggest_questions(session, get_interview_or_404(session, session_id), body.topic)


@router.post("/{session_id}/helper/chat", response_model=list[HelperMessageOut])
def helper_chat(session_id: int, body: HelperChatIn, session: Session = Depends(get_session)):
    """The interviewer asks the helper something; both messages are saved."""
    return helper_service.chat(session, get_interview_or_404(session, session_id), body.text)
