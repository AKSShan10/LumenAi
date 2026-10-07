"""Job profiles (interviewer only). Read and delete only.

Jobs are written, changed and approved in the chat (the assistant and its tools), not here.

  GET    /api/jobs                      list jobs, newest first
  GET    /api/jobs/{job_id}             one job
  DELETE /api/jobs/{job_id}             delete a job
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.jobs.models import Job
from app.features.jobs.schemas import JobOut
from app.features.jobs.services.job_service import get_job_or_404

router = APIRouter(prefix="/api/jobs", tags=["Jobs"], dependencies=[Depends(require_interviewer)])


@router.get("", response_model=list[JobOut])
def list_jobs(session: Session = Depends(get_session)):
    return session.exec(select(Job).order_by(Job.id.desc())).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_session)):
    return get_job_or_404(session, job_id)


@router.delete("/{job_id}", status_code=204)
def remove_job(job_id: int, session: Session = Depends(get_session)):
    session.delete(get_job_or_404(session, job_id))   # an approved description stays in the company documents
    session.commit()
