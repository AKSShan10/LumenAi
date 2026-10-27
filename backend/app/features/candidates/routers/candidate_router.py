"""Candidates (interviewer only).

  GET    /api/jobs/{job_id}/applications/check    how many form answers after the checkpoint are new? Downloads nothing
  POST   /api/jobs/{job_id}/applications/recheck  move the checkpoint back to the start and check every answer again
  POST   /api/jobs/{job_id}/applications/fetch    download the new CVs and save one candidate per form answer
  POST   /api/jobs/{job_id}/candidates/upload     manual upload: one CV file becomes one candidate
  GET    /api/jobs/{job_id}/candidates            the candidates of one job, newest first
  GET    /api/candidates                          the candidates of all jobs, newest first (with the job title)
  GET    /api/candidates/{candidate_id}/cv        the saved CV file of one candidate
  DELETE /api/candidates/{candidate_id}           delete one candidate and the saved CV file
  GET    /api/drive-check                         is the Google Drive access set up? Reads no file
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.candidates.models import Candidate
from app.features.candidates.schemas import CandidateOut, CheckOut, FetchOut, UploadOut
from app.features.candidates.services.application_service import (
    check_applications, drive_check, fetch_applications, reset_checkpoint)
from app.features.candidates.services.cv_storage_service import add_uploaded_cv, candidate_out, cv_file, delete_candidate
from app.features.jobs.models import Job
from app.features.jobs.services.job_service import get_job_or_404

router = APIRouter(prefix="/api", tags=["Candidates"], dependencies=[Depends(require_interviewer)])


# Finds the job (get_job_or_404) and answers 400 if it is not approved yet; CVs need an approved job
def approved_job_or_400(session: Session, job_id: int) -> Job:
    """The job, or 404 when it does not exist, or 400 when it is not approved yet."""
    job = get_job_or_404(session, job_id)
    if job.status != "approved":
        raise HTTPException(400, "Approve the job first. CVs are collected for an approved job.")
    return job


# Loads one candidate from the database or answers 404
def get_candidate_or_404(session: Session, candidate_id: int) -> Candidate:
    """The candidate, or 404 when there is no candidate with this id."""
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


# GET /api/jobs/{job_id}/applications/check: counts new Google Form answers, downloads nothing (check_applications)
@router.get("/jobs/{job_id}/applications/check", response_model=CheckOut)
def check(job_id: int, session: Session = Depends(get_session)):
    """GET /api/jobs/{id}/applications/check: how many new form answers wait (nothing is downloaded)."""
    return check_applications(session, approved_job_or_400(session, job_id))


# POST /api/jobs/{job_id}/applications/recheck: checks every form answer again from the start (reset_checkpoint)
@router.post("/jobs/{job_id}/applications/recheck", response_model=CheckOut)
def recheck(job_id: int, session: Session = Depends(get_session)):
    """POST /api/jobs/{id}/applications/recheck: reads every form answer again from the first one."""
    return reset_checkpoint(session, approved_job_or_400(session, job_id))


# POST /api/jobs/{job_id}/applications/fetch: downloads the new CVs from the Google Form (fetch_applications)
@router.post("/jobs/{job_id}/applications/fetch", response_model=FetchOut)
def fetch(job_id: int, session: Session = Depends(get_session)):
    """POST /api/jobs/{id}/applications/fetch: downloads the new CVs (and photos) and saves the candidates."""
    return fetch_applications(session, approved_job_or_400(session, job_id))


# POST /api/jobs/{job_id}/candidates/upload: saves one uploaded CV file (and the photo, F7) as a new candidate
@router.post("/jobs/{job_id}/candidates/upload", response_model=UploadOut)
def upload(job_id: int, file: UploadFile = File(...), full_name: str = Form(""), email: str = Form(""),
           phone: str = Form(""), photo: UploadFile | None = File(None), session: Session = Depends(get_session)):
    """POST /api/jobs/{id}/candidates/upload: one CV, the contact details and an optional photo."""
    job = approved_job_or_400(session, job_id)
    photo_name, photo_data = (photo.filename or "photo.jpg", photo.file.read()) if photo else ("", b"")
    return add_uploaded_cv(session, job, file.filename or "cv", file.file.read(), full_name[:120], email[:200],
                           phone[:40], photo_name, photo_data)


# GET /api/jobs/{job_id}/candidates: lists the job's candidates, newest first, with their screening result
@router.get("/jobs/{job_id}/candidates", response_model=list[CandidateOut])
def list_candidates(job_id: int, session: Session = Depends(get_session)):
    """GET /api/jobs/{id}/candidates: the job's candidates, newest first, with their screening."""
    get_job_or_404(session, job_id)
    from app.features.screening.models import ScreeningResult
    rows = session.exec(select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.id.desc())).all()
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job_id)).all()}
    return [candidate_out(row, results.get(row.id)) for row in rows]


# GET /api/candidates/{candidate_id}/cv: sends the saved CV file of one candidate (cv_file)
# GET /api/candidates: everyone who applied to any job, newest first, with the job title (the "All jobs" view)
@router.get("/candidates", response_model=list[CandidateOut])
def list_all_candidates(session: Session = Depends(get_session)):
    """GET /api/candidates: the candidates of every job, with the job title."""
    from app.features.jobs.models import Job
    from app.features.screening.models import ScreeningResult
    titles = {job.id: job.title for job in session.exec(select(Job)).all()}
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult)).all()}
    rows = session.exec(select(Candidate).order_by(Candidate.id.desc())).all()
    return [candidate_out(row, results.get(row.id)).model_copy(update={"job_title": titles.get(row.job_id, "")})
            for row in rows]


@router.get("/candidates/{candidate_id}/cv")
def download_cv(candidate_id: int, session: Session = Depends(get_session)):
    """GET /api/candidates/{id}/cv: the saved CV file."""
    candidate = get_candidate_or_404(session, candidate_id)
    path = cv_file(candidate)
    if not path:
        raise HTTPException(404, "No CV file is saved for this candidate")
    return FileResponse(path, filename=candidate.original_file_name or path.name)


# DELETE /api/candidates/{candidate_id}: deletes the candidate and the saved CV file (delete_candidate)
@router.delete("/candidates/{candidate_id}", status_code=204)
def remove_candidate(candidate_id: int, session: Session = Depends(get_session)):
    """DELETE /api/candidates/{id}: deletes the candidate and everything saved about them."""
    delete_candidate(session, get_candidate_or_404(session, candidate_id))


# GET /api/drive-check: tests if the Google Drive access is set up, reads no file (drive_check)
@router.get("/drive-check")
def check_drive():
    """GET /api/drive-check: is the Google Drive access set up? (Settings page)."""
    return drive_check()
