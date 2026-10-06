"""Job profile logic.

    get_job_or_404()        find a job or answer 404
    draft_from_prompt()     the AI turns a short prompt into a job profile (runs the job description workflow)
    update_job()            save changes; a changed job must be approved again
    approve_job()           the interviewer approves; the description can join the company documents
"""
from fastapi import HTTPException
from sqlmodel import Session

from app.features.job_library.services.company_document_service import add_document, has_document_for_job
from app.features.jobs.models import Job
from app.features.jobs.schemas import JobCreate, JobDraftOut
from app.graphs.job_description_graph import write_job_draft
from app.utils.datetime_utils import utc_now


def get_job_or_404(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def draft_from_prompt(prompt: str, change_request: str = "", previous: str = "") -> JobDraftOut:
    result = write_job_draft(prompt, change_request, previous)
    if result["error"]:
        return JobDraftOut(from_ai=False, message="The AI could not write the job: " + result["error"])
    message = "Please check: " + "; ".join(result["problems"]) if result["problems"] else ""
    return JobDraftOut(from_ai=True, message=message, **result["draft"],
                       examples=[e["title"] for e in result["examples"]],
                       policies=[p["title"] for p in result["policies"]], revisions=result["revisions"])


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
