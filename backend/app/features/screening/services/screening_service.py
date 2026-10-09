"""Screening the CVs of one job, and the interviewer's decisions.

    mark_for_screening_again(session, job)    "Screen all again": every CV of the job waits again (the system decides again)
    screen_candidate(session, candidate, job) screens one CV (again)
    decide_candidate(...)                     the interviewer includes or excludes a candidate, or undoes it
    final_status(result)                      included | excluded | needs_review: the person's decision if there is one
    screening_rows(session, job)              every candidate of the job with its result, for the page

Each CV goes through the workflow in app/graphs/cv_screening_graph.py (one run per CV). The workflow reads the saved
CV file itself, saves its result, and then pauses in hr_review until a person decides. In the normal app the
backend screens new CVs by itself in the background (screening_worker.py); nobody has to click.
The AI reads the CV; the rule that decides passed / excluded / needs review is plain code. Nobody is deleted.
"""
import hashlib
import json
import logging

from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.features.candidates.models import Candidate
from app.features.candidates.services.cv_storage_service import cv_file
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult
from app.features.screening.schemas import ScreeningRowOut
from app.features.screening.services.score_service import job_weights
from app.graphs.cv_screening_graph import decide, screen_cv
from app.graphs.cv_screening_prompts import ATS_KEYWORDS_PROMPT

log = logging.getLogger("screening")


def ats_keywords(session: Session, job: Job) -> list[str]:
    """The job's ATS keywords: made by the AI once per job and saved on the job, so every CV of the job is measured
    against the same list (fair and reproducible). Made again only when the job's text changes.
    If the AI cannot answer, the job's own skills are used for now (and the AI is asked again next time)."""
    source = hashlib.sha256(json.dumps([job.title, job.description, job.required_skills, job.preferred_skills,
                                        job.qualifications], default=str).encode()).hexdigest()[:16]
    saved = job.ats_keywords or {}
    if saved.get("source") == source and saved.get("keywords"):
        return list(saved["keywords"])
    answer = llm_json(ATS_KEYWORDS_PROMPT, {"title": job.title, "description": job.description,
                                            "required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
                                            "qualification": job.qualifications})
    words = answer.get("keywords") if isinstance(answer, dict) else None
    if not isinstance(words, list):
        log.warning("ATS keywords for job %s could not be made: %s", job.id, last_error())
        return list(dict.fromkeys(list(job.required_skills or []) + list(job.preferred_skills or [])))
    keywords = list(dict.fromkeys(str(w).strip()[:60] for w in words if str(w).strip()))[:25]
    job.ats_keywords = {"source": source, "keywords": keywords}
    session.add(job)
    session.commit()
    log.info("ATS keywords made for job %s: %d", job.id, len(keywords))
    return keywords


def job_requirements(session: Session, job: Job) -> dict:
    return {"title": job.title, "required_skills": list(job.required_skills or []),
            "preferred_skills": list(job.preferred_skills or []), "min_years": job.min_years or 0,
            "qualifications": (job.qualifications or "").strip(), "weights": job_weights(job),
            "ats_keywords": ats_keywords(session, job)}


def final_status(result: ScreeningResult | None) -> str | None:
    """What counts: the person's decision if there is one, otherwise the system result. None = not screened."""
    if result is None:
        return None
    if result.decision:
        return result.decision
    return {"passed": "included", "excluded": "excluded"}.get(result.result, "needs_review")


def waiting_candidates(session: Session, job: Job) -> list[Candidate]:
    """CVs of the job without a result, or marked by "Screen all again". Oldest first."""
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job.id)).all()}
    candidates = session.exec(select(Candidate).where(Candidate.job_id == job.id).order_by(Candidate.id)).all()
    return [c for c in candidates if c.id not in results or results[c.id].stale]


def screen_candidate(session: Session, candidate: Candidate, job: Job) -> ScreeningResult:
    """Runs the screening workflow for one CV. The workflow's step save_result saves the result."""
    path = cv_file(candidate)
    screen_cv(candidate.id, job.id, job_requirements(session, job), str(path) if path else "")
    session.expire_all()                              # the workflow saved with its own session: read it fresh
    row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).one()
    log.info("screened candidate=%s job=%s result=%s", candidate.id, job.id, row.result)
    return row


def mark_for_screening_again(session: Session, job: Job) -> int:
    """Every screened CV of the job waits again, for example after the requirements changed. The old result stays
    on the page until the new one is ready; then the system decides again (save_result clears a person's decision)."""
    rows = session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job.id)).all()
    for row in rows:
        row.stale = True
        session.add(row)
    session.commit()
    return len(rows)


def decide_candidate(session: Session, candidate: Candidate, decision: str | None, note: str, by: str) -> ScreeningResult:
    """Continues the candidate's paused workflow run (hr_review) with the person's answer."""
    decide(candidate.id, candidate.job_id, decision or "", note, by)
    session.expire_all()
    return session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).one()


def screening_rows(session: Session, job: Job) -> list[ScreeningRowOut]:
    candidates = session.exec(select(Candidate).where(Candidate.job_id == job.id).order_by(Candidate.id)).all()
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult).where(ScreeningResult.job_id == job.id)).all()}
    rows = []
    for candidate in candidates:
        result = results.get(candidate.id)
        row = ScreeningRowOut(candidate_id=candidate.id, full_name=candidate.full_name, waiting=True)
        if result:
            parsed, matches = result.parsed or {}, result.matches or []
            must = [m for m in matches if m["kind"] == "must"]
            nice = [m for m in matches if m["kind"] == "nice"]
            row = ScreeningRowOut(
                candidate_id=candidate.id, full_name=candidate.full_name, result=result.result, reason=result.reason,
                final=final_status(result), waiting=result.stale,
                decision=result.decision, decision_note=result.decision_note, decided_by=result.decided_by,
                decided_at=result.decided_at,
                skills=parsed.get("skills", []), total_years=parsed.get("total_years", 0),
                education=[str(e.get("degree", "")) for e in parsed.get("education", []) if e.get("degree")],
                matches=matches, must_met=sum(m.get("status") == "met" for m in must), must_total=len(must),
                nice_met=sum(m.get("status") == "met" for m in nice), nice_total=len(nice), screened_at=result.screened_at,
                sections=result.sections or {}, weighted_score=result.weighted_score,
                ats=result.ats or {}, ats_score=result.ats_score)
        rows.append(row)
    return rows
