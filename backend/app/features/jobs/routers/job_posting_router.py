"""The posts of a job (interviewer only). Read only: posting is asked for in the chat and done after a Yes.

  GET  /api/jobs/{job_id}/postings     the posts of this job, newest first
  GET  /api/posting-check              is Blogger set up? Posts nothing
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.jobs.models import JobPosting
from app.features.jobs.schemas import PostingOut
from app.features.jobs.services.job_posting_service import posting_check
from app.features.jobs.services.job_service import get_job_or_404

router = APIRouter(prefix="/api", tags=["Job posting"], dependencies=[Depends(require_interviewer)])


# GET /api/jobs/{job_id}/postings: lists the blog posts of the job, newest first
@router.get("/jobs/{job_id}/postings", response_model=list[PostingOut])
def postings(job_id: int, session: Session = Depends(get_session)):
    get_job_or_404(session, job_id)
    return session.exec(select(JobPosting).where(JobPosting.job_id == job_id).order_by(JobPosting.id.desc())).all()


# GET /api/posting-check: tests if Blogger is set up, posts nothing (posting_check)
@router.get("/posting-check")
def check_posting():
    return posting_check()

