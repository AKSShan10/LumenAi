"""Job profile logic. Used by the assistant's tools (recruitment_server.py) and by the Yes / No answers.

    get_job_or_404()        find a job or answer 404
    create_job()            save a new job as a draft
    update_job()            save changes; a changed job must be approved again
    approve_job()           the interviewer approves; the description can join the company documents
"""
from fastapi import HTTPException
from sqlmodel import Session

from app.features.job_library.services.company_document_service import add_document, has_document_for_job
from app.features.jobs.models import Job
from app.features.jobs.schemas import JobCreate
from app.utils.datetime_utils import utc_now


def get_job_or_404(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def create_job(session: Session, body: JobCreate) -> Job:
    job = Job(**body.model_dump())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def update_job(session: Session, job: Job, body: JobCreate) -> Job:
    changes = body.model_dump()
    changed = any(getattr(job, field) != value for field, value in changes.items())
    for field, value in changes.items():
        setattr(job, field, value)
    if changed:                       # an edited job must be approved again before it is posted
        job.status, job.approved_at = "draft", None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def approve_job(session: Session, job: Job, add_to_library: bool) -> Job:
    if not (job.description or "").strip():
        raise HTTPException(400, "Write or generate the job description before approving")
    job.status, job.approved_at = "approved", utc_now()
    session.add(job)
    session.commit()
    if add_to_library and not has_document_for_job(session, job.id):
        add_document(session, job.title, job.description, kind="job_description", source="approved job", job_id=job.id)
    session.refresh(job)
    return job
