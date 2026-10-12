"""System checks for the interviewer.

  GET /api/llm-check       makes one tiny call to the AI service and says in plain words whether it works
  GET /api/email-check     checks the email (SMTP) settings and login through the email MCP server; sends nothing
  GET /api/workflow-runs   the latest runs of the recruitment graph (stage, outcome, error, seconds)
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.ai.llm_client import check_connection
from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.interviews.services.invitation_service import email_check as check_email
from app.features.system.models import WorkflowRun

router = APIRouter(prefix="/api", tags=["System"], dependencies=[Depends(require_interviewer)])


@router.get("/llm-check")
def llm_check():
    return check_connection()


@router.get("/email-check")
def email_check():
    return check_email()


@router.get("/workflow-runs")
def workflow_runs(limit: int = Query(default=20, ge=1, le=200), session: Session = Depends(get_session)):
    rows = session.exec(select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(limit)).all()
    return [r.model_dump() for r in rows]
