"""Screening (interviewer only).

New CVs are screened by the backend by itself (screening_worker.py). These endpoints are for the rest:

  POST /api/jobs/{job_id}/screening             screen the CVs that wait; {"again": true} = screen every CV again
                                                (the system decides again; decisions made by a person are cleared)
  GET  /api/jobs/{job_id}/screening             every candidate of the job with the screening result
  GET  /api/jobs/{job_id}/screening/status      the progress of the latest screening run (for the progress bar)
  POST /api/candidates/{candidate_id}/screening screen one candidate again
  PUT  /api/candidates/{candidate_id}/decision  the interviewer includes / excludes the candidate, or undoes it
  GET  /api/jobs/{job_id}/score-weights         the job's scoring weights (skills, experience, qualifications)
  PUT  /api/jobs/{job_id}/score-weights         new weights (they add up to 100); every weighted score is recalculated
  GET    /api/jobs/{job_id}/shortlist           the shortlist of the job (included candidates chosen for the interview)
  POST   /api/jobs/{job_id}/shortlist           put included candidates on it: {candidate_ids, rule, value}
  DELETE /api/candidates/{candidate_id}/shortlist   take one candidate off it
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core import config
from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.candidates.models import Candidate
from app.features.jobs.models import Job
from app.features.jobs.services.job_service import get_job_or_404
from app.features.screening.models import ScreeningResult
from app.features.screening.schemas import (
    DecisionIn, ProgressOut, ScreenIn, ScreenOut, ScreeningRowOut, ShortlistAddOut, ShortlistIn, ShortlistRowOut, WeightsIn,
    WeightsOut)
from app.features.screening.services.score_service import job_weights, set_weights
from app.features.screening.services.screening_service import (
    decide_candidate, final_status, mark_for_screening_again, screen_candidate, screening_rows, waiting_candidates)
from app.features.screening.services.screening_worker import progress_of, screen_waiting, start_screening
from app.features.screening.services.shortlist_service import add_to_shortlist, remove_from_shortlist, shortlist_rows

router = APIRouter(prefix="/api", tags=["Screening"], dependencies=[Depends(require_interviewer)])

WORDS = {"included": "included", "excluded": "excluded", "needs_review": "needs a look"}


# Finds the job (get_job_or_404) and answers 400 if it is not approved; screening needs approval
def approved_job_or_400(session: Session, job_id: int) -> Job:
    job = get_job_or_404(session, job_id)
    if job.status != "approved":
        raise HTTPException(400, "Approve the job first. CVs are screened for an approved job.")
    return job


# Loads one candidate from the database or answers 404
def get_candidate_or_404(session: Session, candidate_id: int) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


# Turns a screening run's progress into a sentence for the page, like "Screening 3 of 7 CV(s)..."
def summary(run: dict) -> str:
    if run["running"]:
        return f"Screening {run['done']} of {run['total']} CV(s)..."
    if not run["finished_at"]:
        return ""
    return (f"Screening finished: {run['done']} CV(s), {run['included']} included, {run['excluded']} excluded"
            + (f", {run['needs_review']} need(s) a look." if run["needs_review"] else "."))


# POST /api/jobs/{job_id}/screening: screens the waiting CVs (start_screening, or screen_waiting in tests)
@router.post("/jobs/{job_id}/screening", response_model=ScreenOut)
def screen(job_id: int, body: ScreenIn | None = None, session: Session = Depends(get_session)):
    job = approved_job_or_400(session, job_id)
    if body and body.again:
        mark_for_screening_again(session, job)
    if config.SCREENING_MODE == "background":
        waiting = start_screening(job.id)
        return ScreenOut(ok=True, message=f"Screening started for {waiting} CV(s)." if waiting
                         else "Every CV of this job is screened already.", left=waiting)
    if not waiting_candidates(session, job):
        return ScreenOut(ok=True, message="Every CV of this job is screened already.")
    run = screen_waiting(job.id)                       # manual mode (tests): screen now and wait
    return ScreenOut(ok=True, message=summary(run), screened=run["done"])


# GET /api/jobs/{job_id}/screening/status: returns the screening progress for the bar (progress_of)
@router.get("/jobs/{job_id}/screening/status", response_model=ProgressOut)
def status(job_id: int, session: Session = Depends(get_session)):
    get_job_or_404(session, job_id)
    run = progress_of(job_id)
    return ProgressOut(**run, message=summary(run))


# GET /api/jobs/{job_id}/screening: lists every candidate of the job with its result (screening_rows)
@router.get("/jobs/{job_id}/screening", response_model=list[ScreeningRowOut])
def results(job_id: int, session: Session = Depends(get_session)):
    return screening_rows(session, get_job_or_404(session, job_id))


# POST /api/candidates/{candidate_id}/screening: screens one candidate again now (screen_candidate)
@router.post("/candidates/{candidate_id}/screening", response_model=ScreenOut)
def screen_one(candidate_id: int, session: Session = Depends(get_session)):
    candidate = get_candidate_or_404(session, candidate_id)
    result = screen_candidate(session, candidate, approved_job_or_400(session, candidate.job_id))
    name = candidate.full_name or "The candidate"
    return ScreenOut(ok=True, message=f"Done: {name} is {WORDS[final_status(result)]}. {result.reason}", screened=1)


# PUT /api/candidates/{candidate_id}/decision: saves or undoes the interviewer's decision (decide_candidate)
@router.put("/candidates/{candidate_id}/decision", response_model=ScreenOut)
def decision(candidate_id: int, body: DecisionIn, session: Session = Depends(get_session),
             email: str = Depends(current_email)):
    candidate = get_candidate_or_404(session, candidate_id)
    approved_job_or_400(session, candidate.job_id)
    if not session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first():
        raise HTTPException(400, "This CV is not screened yet. Wait for the screening, then decide.")
    result = decide_candidate(session, candidate, body.decision, body.note, email)
    name = candidate.full_name or "The candidate"
    if result.decision:
        return ScreenOut(ok=True, message=f"{name} is now {result.decision} (your decision).")
    return ScreenOut(ok=True, message=f"Your decision was undone. {name} is {WORDS[final_status(result)]} again "
                                      "(the system result).")


# GET /api/jobs/{job_id}/score-weights: returns the job's scoring weights (job_weights)
@router.get("/jobs/{job_id}/score-weights", response_model=WeightsOut)
def get_weights(job_id: int, session: Session = Depends(get_session)):
    return WeightsOut(**job_weights(get_job_or_404(session, job_id)))


# PUT /api/jobs/{job_id}/score-weights: saves new weights and recalculates every score (set_weights)
@router.put("/jobs/{job_id}/score-weights", response_model=WeightsOut)
def put_weights(job_id: int, body: WeightsIn, session: Session = Depends(get_session)):
    job = get_job_or_404(session, job_id)
    updated = set_weights(session, job, body.model_dump())
    return WeightsOut(**job_weights(job), updated=updated)


# GET /api/jobs/{job_id}/shortlist: returns the job's shortlist, best score first (shortlist_rows)
@router.get("/jobs/{job_id}/shortlist", response_model=list[ShortlistRowOut])
def get_shortlist(job_id: int, session: Session = Depends(get_session)):
    return shortlist_rows(session, get_job_or_404(session, job_id))


# POST /api/jobs/{job_id}/shortlist: puts included candidates on the shortlist (add_to_shortlist)
@router.post("/jobs/{job_id}/shortlist", response_model=ShortlistAddOut)
def add_shortlist(job_id: int, body: ShortlistIn, session: Session = Depends(get_session),
                  email: str = Depends(current_email)):
    job = approved_job_or_400(session, job_id)
    return add_to_shortlist(session, job, body.candidate_ids, body.rule, body.value, email)


# DELETE /api/candidates/{candidate_id}/shortlist: takes one candidate off the shortlist
@router.delete("/candidates/{candidate_id}/shortlist", status_code=204)
def remove_shortlist(candidate_id: int, session: Session = Depends(get_session)):
    remove_from_shortlist(session, get_candidate_or_404(session, candidate_id).id)
