"""Job profiles (interviewer only).

  POST   /api/jobs                      create a job
  GET    /api/jobs                      list jobs, newest first
  GET    /api/jobs/{job_id}             one job
  PUT    /api/jobs/{job_id}             edit a job (an approved job becomes a draft again)
  DELETE /api/jobs/{job_id}             delete a job
  POST   /api/jobs/draft-from-prompt    the AI turns a short prompt into a job profile (not saved yet)
  POST   /api/jobs/{job_id}/approve     the interviewer approves the job
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.jobs.models import Job
from app.features.jobs.schemas import ApproveIn, JobCreate, JobDraftOut, JobOut, PromptIn
from app.features.jobs.services.job_service import approve_job, draft_from_prompt, get_job_or_404, update_job

router = APIRouter(prefix="/api/jobs", tags=["Jobs"], dependencies=[Depends(require_interviewer)])


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobCreate, session: Session = Depends(get_session)):
    job = Job(**body.model_dump())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(session: Session = Depends(get_session)):
    return session.exec(select(Job).order_by(Job.id.desc())).all()


@router.post("/draft-from-prompt", response_model=JobDraftOut)
def job_from_prompt(body: PromptIn):
    return draft_from_prompt(body.prompt, body.change_request, body.previous)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_session)):
    return get_job_or_404(session, job_id)


@router.put("/{job_id}", response_model=JobOut)
def edit_job(job_id: int, body: JobCreate, session: Session = Depends(get_session)):
    return update_job(session, get_job_or_404(session, job_id), body)


@router.delete("/{job_id}", status_code=204)
def remove_job(job_id: int, session: Session = Depends(get_session)):
    session.delete(get_job_or_404(session, job_id))   # an approved description stays in the company documents
    session.commit()


@router.post("/{job_id}/approve", response_model=JobOut)
def approve(job_id: int, body: ApproveIn | None = None, session: Session = Depends(get_session)):
    return approve_job(session, get_job_or_404(session, job_id), (body or ApproveIn()).add_to_library)
