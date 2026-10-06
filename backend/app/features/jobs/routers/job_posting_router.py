"""Posting an approved job to the Telegram channel (interviewer only).

  GET  /api/jobs/{job_id}/post-text    the post made by code from the approved job (no AI)
  POST /api/jobs/{job_id}/post-draft   optional: the AI writes a shorter post (not saved, not posted)
  POST /api/jobs/{job_id}/post         post it to the channel; the result is saved
  GET  /api/jobs/{job_id}/postings     earlier posts of this job, newest first
  GET  /api/telegram-check             is the bot set up? Posts nothing
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.jobs.models import JobPosting
from app.features.jobs.schemas import PostDraftIn, PostDraftOut, PostIn, PostingOut, PostTextOut
from app.features.jobs.services.job_posting_service import approved_post, draft_post, post_job, telegram_check
from app.features.jobs.services.job_service import get_job_or_404

router = APIRouter(prefix="/api", tags=["Job posting"], dependencies=[Depends(require_interviewer)])


@router.get("/jobs/{job_id}/post-text", response_model=PostTextOut)
def post_text(job_id: int, session: Session = Depends(get_session)):
    return PostTextOut(text=approved_post(get_job_or_404(session, job_id)))


@router.post("/jobs/{job_id}/post-draft", response_model=PostDraftOut)
def write_post(job_id: int, body: PostDraftIn | None = None, session: Session = Depends(get_session)):
    body = body or PostDraftIn()
    return draft_post(get_job_or_404(session, job_id), body.change_request, body.previous)


@router.post("/jobs/{job_id}/post", response_model=PostingOut)
def post(job_id: int, body: PostIn, session: Session = Depends(get_session)):
    return post_job(session, get_job_or_404(session, job_id), body.text, body.apply_url)


@router.get("/jobs/{job_id}/postings", response_model=list[PostingOut])
def postings(job_id: int, session: Session = Depends(get_session)):
    get_job_or_404(session, job_id)
    return session.exec(select(JobPosting).where(JobPosting.job_id == job_id).order_by(JobPosting.id.desc())).all()


@router.get("/telegram-check")
def check_telegram():
    return telegram_check()
