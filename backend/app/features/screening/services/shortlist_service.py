"""The shortlist: the included candidates the interviewer chose for the interview invitation (table shortlist_entry).

    rule_text(rule, value)          "Top 5", "Final score at least 70" or "Added by hand", saved with each candidate
    add_to_shortlist(...)           puts included candidates of one job on the shortlist (the interviewer's click)
    remove_from_shortlist(...)      takes one candidate off it (the interviewer's click)
    remove_unless_included(...)     takes a candidate off it when they are no longer included (the screening workflow)
    shortlist_rows(session, job)    the shortlist of a job, highest final score first, for the page

The page chooses whom to add with its filter (Top K or a minimum final score) or the Shortlist link of one row.
Plain code only: the AI is not asked, and only a person adds or removes someone. Every change writes one row to
workflow_run (stage "shortlist").
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult, ShortlistEntry
from app.features.screening.schemas import ShortlistAddOut, ShortlistRowOut
from app.features.system.models import WorkflowRun


def rule_text(rule: str, value: float | None) -> str:
    if rule == "top":
        return f"Top {int(value)}"
    if rule == "min_score":
        return f"Final score at least {value:g}"
    return "Added by hand"


def _log(session: Session, candidate_id: int, outcome: str) -> None:
    session.add(WorkflowRun(stage="shortlist", subject_id=candidate_id, outcome=outcome, seconds=0.0))


def add_to_shortlist(session: Session, job: Job, candidate_ids: list[int], rule: str, value: float | None,
                     by: str) -> ShortlistAddOut:
    """Every id must be an included candidate of this job, otherwise nothing is added and the answer says why.
    A candidate who is on the shortlist already is skipped."""
    from app.features.screening.services.screening_service import final_status    # (screening_service uses the workflow)

    ids = list(dict.fromkeys(candidate_ids))                       # the same id twice counts once
    candidates = {c.id: c for c in session.exec(select(Candidate).where(Candidate.id.in_(ids))).all()}
    results = {r.candidate_id: r for r in session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id.in_(ids))).all()}
    for candidate_id in ids:
        candidate = candidates.get(candidate_id)
        if not candidate or candidate.job_id != job.id:
            raise HTTPException(400, f"Candidate {candidate_id} is not a candidate of this job.")
        result = results.get(candidate_id)
        if result is None or result.stale or final_status(result) != "included":
            name = candidate.full_name or f"Candidate {candidate.number}"
            raise HTTPException(400, f"{name} is not included, so they cannot be put on the shortlist.")

    already = set(session.exec(select(ShortlistEntry.candidate_id).where(ShortlistEntry.candidate_id.in_(ids))).all())
    text = rule_text(rule, value)
    new = [candidate_id for candidate_id in ids if candidate_id not in already]
    for candidate_id in new:
        session.add(ShortlistEntry(job_id=job.id, candidate_id=candidate_id, rule=text, added_by=by))
        _log(session, candidate_id, f"added ({text})")
    session.commit()

    message = f"{len(new)} candidate(s) put on the shortlist ({text})." if new else "Nobody new: they are on the shortlist already."
    if new and already:
        message += f" {len(already)} were on it already."
    return ShortlistAddOut(ok=True, message=message, added=len(new), already=len(already))


def remove_from_shortlist(session: Session, candidate_id: int) -> None:
    entry = session.exec(select(ShortlistEntry).where(ShortlistEntry.candidate_id == candidate_id)).first()
    if not entry:
        raise HTTPException(404, "This candidate is not on the shortlist.")
    session.delete(entry)
    _log(session, candidate_id, "removed by a person")
    session.commit()


def remove_unless_included(session: Session, candidate_id: int, final: str) -> None:
    """Called by the screening workflow when a result or a decision is saved (the caller commits).
    final is what counts now: included | excluded | needs_review. Only an included candidate may stay on the
    shortlist, so the interview invitation can never go to someone who is not included."""
    if final == "included":
        return
    entry = session.exec(select(ShortlistEntry).where(ShortlistEntry.candidate_id == candidate_id)).first()
    if entry:
        session.delete(entry)
        _log(session, candidate_id, f"removed (now {final.replace('_', ' ')})")


def shortlist_rows(session: Session, job: Job) -> list[ShortlistRowOut]:
    entries = session.exec(select(ShortlistEntry).where(ShortlistEntry.job_id == job.id)).all()
    ids = [entry.candidate_id for entry in entries]
    candidates = {c.id: c for c in session.exec(select(Candidate).where(Candidate.id.in_(ids))).all()}
    scores = {r.candidate_id: r.weighted_score
              for r in session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id.in_(ids))).all()}
    rows = []
    for entry in entries:
        candidate = candidates.get(entry.candidate_id)
        if candidate:
            rows.append(ShortlistRowOut(candidate_id=candidate.id, number=candidate.number, full_name=candidate.full_name,
                                        email=candidate.email, weighted_score=scores.get(candidate.id), rule=entry.rule,
                                        added_by=entry.added_by, added_at=entry.added_at))
    # highest final score first; the same score keeps the candidate order (the same list every time)
    rows.sort(key=lambda row: (-(row.weighted_score if row.weighted_score is not None else -1), row.number))
    return rows
