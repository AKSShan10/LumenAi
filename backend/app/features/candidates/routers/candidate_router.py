"""Candidates (interviewer only).

  GET    /api/jobs/{job_id}/applications/check    how many form answers after the checkpoint are new? Downloads nothing
  POST   /api/jobs/{job_id}/applications/recheck  move the checkpoint back to the start and check every answer again
  POST   /api/jobs/{job_id}/applications/fetch    download the new CVs and save one candidate per form answer
  POST   /api/jobs/{job_id}/candidates/upload     manual upload: one CV file becomes one candidate
  GET    /api/jobs/{job_id}/candidates            the candidates of one job, newest first
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


def approved_job_or_400(session: Session, job_id: int) -> Job:
    job = get_job_or_404(session, job_id)
    if job.status != "approved":
        raise HTTPException(400, "Approve the job first. CVs are collected for an approved job.")
    return job


def get_candidate_or_404(session: Session, candidate_id: int) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


@router.get("/jobs/{job_id}/applications/check", response_model=CheckOut)
def check(job_id: int, session: Session = Depends(get_session)):
    return check_applications(session, approved_job_or_400(session, job_id))


@router.post("/jobs/{job_id}/applications/recheck", response_model=CheckOut)
def recheck(job_id: int, session: Session = Depends(get_session)):
    return reset_checkpoint(session, approved_job_or_400(session, job_id))


@router.post("/jobs/{job_id}/applications/fetch", response_model=FetchOut)
def fetch(job_id: int, session: Session = Depends(get_session)):
    return fetch_applications(session, approved_job_or_400(session, job_id))


@router.post("/jobs/{job_id}/candidates/upload", response_model=UploadOut)
def upload(job_id: int, file: UploadFile = File(...), full_name: str = Form(""), email: str = Form(""),
           phone: str = Form(""), session: Session = Depends(get_session)):
    job = approved_job_or_400(session, job_id)
    return add_uploaded_cv(session, job, file.filename or "cv", file.file.read(), full_name[:120], email[:200], phone[:40])


@router.get("/jobs/{job_id}/candidates", response_model=list[CandidateOut])
def list_candidates(job_id: int, session: Session = Depends(get_session)):
    get_job_or_404(session, job_id)
    from app.features.screening.models import ScreeningResult
    rows = session.exec(select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.id.desc())).all()
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job_id)).all()}
    return [candidate_out(row, results.get(row.id)) for row in rows]


@router.get("/candidates/{candidate_id}/cv")
def download_cv(candidate_id: int, session: Session = Depends(get_session)):
    candidate = get_candidate_or_404(session, candidate_id)
    path = cv_file(candidate)
    if not path:
        raise HTTPException(404, "No CV file is saved for this candidate")
    return FileResponse(path, filename=candidate.original_file_name or path.name)


@router.delete("/candidates/{candidate_id}", status_code=204)
def remove_candidate(candidate_id: int, session: Session = Depends(get_session)):
    delete_candidate(session, get_candidate_or_404(session, candidate_id))


@router.get("/drive-check")
def check_drive():
    return drive_check()
