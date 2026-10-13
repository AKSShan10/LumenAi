"""The weighted score (F4): plain Python, no AI.

    weighted_score(sections, weights)    the three section scores combined with the job's weights
    set_weights(session, job, weights)   saves new weights and recalculates every candidate of the job

The AI gives each section a score of 0-100 once, during the screening. The weighted score is only arithmetic on
those saved numbers, so new weights change every candidate at once, without asking the AI again, and the same
numbers always give the same result (reproducible).
"""
from sqlmodel import Session, select

from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult

SECTIONS = ("skills", "experience", "qualifications")


# Returns the job's three scoring weights (skills, experience, qualifications) as a dict
def job_weights(job: Job) -> dict:
    return {"skills": job.weight_skills, "experience": job.weight_experience, "qualifications": job.weight_qualifications}


def weighted_score(sections: dict, weights: dict) -> float | None:
    """sum(score x weight) / sum(weights). None if a section has no score."""
    if not sections or any(not isinstance(sections.get(name, {}).get("score"), int) for name in SECTIONS):
        return None
    total = sum(weights[name] for name in SECTIONS)
    if total <= 0:
        return None
    return round(sum(sections[name]["score"] * weights[name] for name in SECTIONS) / total, 1)


def set_weights(session: Session, job: Job, weights: dict) -> int:
    """Saves the weights on the job and recalculates the weighted score of every screened candidate. Returns how many."""
    job.weight_skills, job.weight_experience, job.weight_qualifications = (weights[name] for name in SECTIONS)
    session.add(job)
    rows = session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job.id)).all()
    for row in rows:
        row.weighted_score = weighted_score(row.sections or {}, weights)
        session.add(row)
    session.commit()
    return len(rows)
