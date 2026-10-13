"""The candidate's profile in the interviewer's call tab: who the candidate is and how their CV was screened.

    candidate_profile(session, interview)    the application details, the screening result, the job's weights,
                                             and the jobs and degrees the AI read from the CV (for "Key highlights")

Only the interviewer's route uses this (login needed). The candidate's page never gets it:
no scores, reasons or notes are shown to the candidate.
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.candidates.services.cv_storage_service import candidate_out
from app.features.interviews.models import InterviewSession
from app.features.interviews.schemas import ProfileOut
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult
from app.features.screening.services.score_service import job_weights
from app.features.screening.services.screening_service import screening_row


# Collects the candidate details, screening result, job weights and CV jobs/degrees for the call tab
def candidate_profile(session: Session, interview: InterviewSession) -> ProfileOut:
    candidate = session.get(Candidate, interview.candidate_id)
    if not candidate:
        raise HTTPException(404, "The candidate of this interview was deleted.")
    job = session.get(Job, interview.job_id)
    result = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first()
    parsed = (result.parsed or {}) if result else {}
    return ProfileOut(candidate=candidate_out(candidate, result), job_title=job.title if job else "",
                      weights=job_weights(job) if job else {}, screening=screening_row(candidate, result) if result else None,
                      jobs=_clean(parsed.get("experience"), ("title", "company", "years")),
                      degrees=_clean(parsed.get("education"), ("degree", "institute")))


def _clean(items, keys: tuple) -> list[dict]:
    """Only the fields the panel shows, and only rows the AI really filled in (it can return odd shapes)."""
    rows = []
    for item in items or []:
        if isinstance(item, dict):
            row = {key: "" if item.get(key) is None else item.get(key) for key in keys}
            if row.get(keys[0]):
                rows.append(row)
    return rows[:10]
