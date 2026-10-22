"""System checks for the interviewer.

  GET /api/llm-check       makes one tiny call to the AI service and says in plain words whether it works
  GET /api/llm-model       the AI model in use, the default (LLM_MODEL) and the allowed list (LLM_MODEL_CHOICES)
  PUT /api/llm-model       {model}: choose another allowed model; the next AI call uses it (no restart)
  GET /api/email-check     checks the email (SMTP) settings and login; sends nothing
  GET /api/video-check     are the LiveKit settings there, and can a call ticket be made? connects to nothing
  GET /api/stt-check       is speech-to-text set up, and does Deepgram accept the key? sends no sound
  GET /api/workflow-runs   the latest runs of the recruitment graph (stage, outcome, error, seconds)
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.llm_client import check_connection
from app.ai.model_choice import choose_model, model_info
from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.interviews.services.smtp_service import check_email_settings as check_email
from app.features.transcripts.services.stt_service import stt_check as check_stt
from app.features.interviews.services.video_service import video_check as check_video
from app.features.system.models import WorkflowRun

router = APIRouter(prefix="/api", tags=["System"], dependencies=[Depends(require_interviewer)])


# GET /api/llm-check: makes one tiny AI call and says if the AI service works (check_connection)
@router.get("/llm-check")
def llm_check():
    return check_connection()


class ModelIn(BaseModel):
    model: str


# GET /api/llm-model: the model in use, the default and the allowed list (Settings page)
@router.get("/llm-model")
def llm_model():
    return model_info()


# PUT /api/llm-model: the interviewer chooses another allowed model
@router.put("/llm-model")
def change_llm_model(body: ModelIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return choose_model(session, body.model.strip(), email)


# GET /api/email-check: checks the email (SMTP) settings and login; sends nothing
@router.get("/email-check")
def email_check():
    return check_email()


# GET /api/video-check: checks the LiveKit settings by making a test ticket; connects to nothing
@router.get("/video-check")
def video_check():
    return check_video()


# GET /api/stt-check: checks the speech-to-text settings and key; sends no sound
@router.get("/stt-check")
def stt_check():
    return check_stt()


# GET /api/workflow-runs: returns the latest WorkflowRun rows, newest first
@router.get("/workflow-runs")
def workflow_runs(limit: int = Query(default=20, ge=1, le=200), session: Session = Depends(get_session)):
    rows = session.exec(select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(limit)).all()
    return [r.model_dump() for r in rows]
