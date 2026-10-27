"""The talent pool: keep a past candidate, list the pool, find who fits a new job, and the unsubscribe link.

    entry(session, candidate)          is the candidate in the pool? (card on the assessment report)
    add(session, candidate, body, by)  keeps the candidate for future jobs (or changes the status and note);
                                       someone who unsubscribed only with add_back (the interviewer confirmed it)
    remove(session, candidate)         takes the candidate out (their invitations too)
    pool(session)                      everyone in the pool, newest first (Talent Pool page)
    skill_match(job, candidate, cv_skills)  the match of one CV with one job (code only, see below)
    matches(session, job, filters)     pool candidates who may fit a job, best match first, with the filters
    unsubscribe_info / unsubscribe     the public "no more emails" link

Fair matching: only the job's skills and the skills shown in the CV are used. The name, email, phone, gender, age,
address, nationality, school and the earlier score never change the match or the order.
"""
import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core import config
from app.features.assessments.models import Assessment
from app.features.candidates.models import Candidate
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult
from app.features.talent_pool.models import TalentInvite, TalentPoolEntry
from app.features.talent_pool.schemas import (InviteSent, MatchRow, PoolEntryIn, PoolEntryOut, PoolRow,
                                              UnsubscribeOut)
from app.utils.datetime_utils import as_utc, utc_now
from app.utils.skill_names import find_skill, skill_key

log = logging.getLogger("talent_pool")


REQUIRED_WEIGHT, PREFERRED_WEIGHT = 2, 1     # a required skill counts twice as much as a preferred one


# active | unsubscribed | expired
def state(entry: TalentPoolEntry) -> str:
    if entry.unsubscribed_at:
        return "unsubscribed"
    return "expired" if as_utc(entry.keep_until) < utc_now() else "active"


def _entry_of(session: Session, candidate_id: int) -> TalentPoolEntry | None:
    return session.exec(select(TalentPoolEntry).where(TalentPoolEntry.candidate_id == candidate_id)).first()


# Has this email applied to the job? (an invitation counts as "applied" when it did)
def _applied(session: Session, email: str, job_id: int) -> bool:
    if not email.strip():
        return False
    return any(c.email.strip().lower() == email.strip().lower()
               for c in session.exec(select(Candidate).where(Candidate.job_id == job_id)).all())


def entry(session: Session, candidate: Candidate) -> PoolEntryOut:
    row = _entry_of(session, candidate.id)
    if not row:
        return PoolEntryOut(in_pool=False)
    return PoolEntryOut(in_pool=True, status=row.status, note=row.note, added_at=row.added_at,
                        keep_until=row.keep_until, unsubscribed=row.unsubscribed_at is not None)


def add(session: Session, candidate: Candidate, body: PoolEntryIn, by: str) -> PoolEntryOut:
    """Keeps the candidate for POOL_KEEP_DAYS days. Someone who unsubscribed is added again only when the interviewer
    confirms it (add_back): they get a new unsubscribe link and a new keep-until date."""
    row = _entry_of(session, candidate.id)
    if row and row.unsubscribed_at:
        if not body.add_back:
            raise HTTPException(409, "This person asked not to be contacted about future openings. Use \"Add back\" "
                                     "only if they asked to be contacted again.")
        row.unsubscribed_at, row.added_by = None, by
        row.unsubscribe_token = secrets.token_urlsafe(24)          # the old link no longer works
        row.keep_until = utc_now() + timedelta(days=config.POOL_KEEP_DAYS)
        log.info("talent pool add back candidate=%s", candidate.id)
    if not row:
        row = TalentPoolEntry(candidate_id=candidate.id, added_by=by, unsubscribe_token=secrets.token_urlsafe(24),
                              keep_until=utc_now() + timedelta(days=config.POOL_KEEP_DAYS))
    row.status, row.note = body.status, body.note.strip()
    session.add(row)
    session.commit()
    log.info("talent pool add candidate=%s status=%s", candidate.id, row.status)
    return entry(session, candidate)


def remove(session: Session, candidate: Candidate) -> PoolEntryOut:
    row = _entry_of(session, candidate.id)
    if row:
        for invite in session.exec(select(TalentInvite).where(TalentInvite.pool_id == row.id)).all():
            session.delete(invite)
        session.delete(row)
        session.commit()
        log.info("talent pool remove candidate=%s", candidate.id)
    return PoolEntryOut(in_pool=False)


def pool(session: Session) -> list[PoolRow]:
    rows = []
    for row in session.exec(select(TalentPoolEntry).order_by(TalentPoolEntry.added_at.desc())).all():
        candidate = session.get(Candidate, row.candidate_id)
        if not candidate:
            continue
        job = session.get(Job, candidate.job_id)
        invites = []
        for invite in session.exec(select(TalentInvite).where(TalentInvite.pool_id == row.id)
                                   .order_by(TalentInvite.sent_at)).all():
            new_job = session.get(Job, invite.job_id)
            invites.append(InviteSent(job_title=new_job.title if new_job else "(deleted job)", sent_at=invite.sent_at,
                                      applied=_applied(session, candidate.email, invite.job_id)))
        rows.append(PoolRow(candidate_id=candidate.id, name=candidate.full_name, email=candidate.email,
                            from_job=job.title if job else "", status=row.status, note=row.note, added_at=row.added_at,
                            keep_until=row.keep_until, state=state(row), invites=invites))
    return rows


def skill_match(job: Job, cv_text: str, cv_skills: list) -> dict:
    """The match of one CV with one job, worked out by code only:
      - a skill counts when the CV shows it, also under another name ("Postgres" = "PostgreSQL", see skill_names.py)
      - each skill counts once, however often the CV repeats it
      - match % = found weight / all weight; a required skill weighs 2, a preferred one 1
    Nothing else about the person is used."""
    required = list(dict.fromkeys(job.required_skills or []))
    known = {skill_key(r) for r in required}
    preferred = [p for p in dict.fromkeys(job.preferred_skills or []) if skill_key(p) not in known]
    skills = [(r, REQUIRED_WEIGHT) for r in required] + [(p, PREFERRED_WEIGHT) for p in preferred]
    matched = [name for name, _ in skills if find_skill(name, cv_skills, cv_text)]
    total = sum(weight for _, weight in skills)
    found = sum(weight for name, weight in skills if name in matched)
    return {"match": round(100 * found / total) if total else 0, "matched": matched,
            "missing": [name for name, _ in skills if name not in matched],
            "all_required": all(r in matched for r in required)}


def matches(session: Session, job: Job, min_match: int | None = None, all_required: bool = False,
            min_score: float | None = None, status: str | None = None, hide_invited: bool = False) -> list[MatchRow]:
    """Active pool candidates who may fit the job, best match first (equal matches by name).
    Never listed: their own job, people who already applied to this job, unsubscribed and expired entries.
    Filters (the interviewer changes them on the page):
      min_match      at least this match % (empty = POOL_MIN_MATCH from .env); 0 = everyone with at least one skill
      all_required   the CV must show every required skill
      min_score      their earlier overall score at least this (people without an assessment are then left out)
      status         strong | other_role
      hide_invited   leave out people already invited to this job"""
    limit = config.POOL_MIN_MATCH if min_match is None else min_match
    rows = []
    for row in session.exec(select(TalentPoolEntry)).all():
        candidate = session.get(Candidate, row.candidate_id)
        if not candidate or state(row) != "active" or candidate.job_id == job.id:
            continue
        if _applied(session, candidate.email, job.id):
            continue                                     # already an applicant of this job
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first()
        cv_skills = list((screening.parsed or {}).get("skills") or []) if screening else []
        fit = skill_match(job, candidate.cv_text or "", cv_skills)
        if not fit["matched"] or fit["match"] < limit or (all_required and not fit["all_required"]):
            continue
        report = session.exec(select(Assessment).where(Assessment.candidate_id == candidate.id)).first()
        score = report.overall_score if report else None
        if min_score is not None and (score is None or score < min_score):
            continue
        if status and row.status != status:
            continue
        invite = session.exec(select(TalentInvite).where(TalentInvite.pool_id == row.id, TalentInvite.job_id == job.id)
                              .order_by(TalentInvite.sent_at.desc())).first()
        if hide_invited and invite:
            continue
        earlier = session.get(Job, candidate.job_id)
        rows.append(MatchRow(pool_id=row.id, candidate_id=candidate.id, name=candidate.full_name,
                             from_job=earlier.title if earlier else "", status=row.status, overall_score=score,
                             decision=report.decision if report else "", match=fit["match"],
                             matched=fit["matched"], missing=fit["missing"],
                             invited_at=invite.sent_at if invite else None))
    rows.sort(key=lambda r: (-r.match, r.name.lower()))     # only the match decides the order
    return rows


# ---------- the public unsubscribe link ----------

def _by_token(session: Session, token: str) -> TalentPoolEntry:
    row = session.exec(select(TalentPoolEntry).where(TalentPoolEntry.unsubscribe_token == token)).first() \
        if len(token) >= 20 else None
    if not row:
        raise HTTPException(404, "This link is not valid.")
    return row


def unsubscribe_info(session: Session, token: str) -> UnsubscribeOut:
    row = _by_token(session, token)
    candidate = session.get(Candidate, row.candidate_id)
    first = (candidate.full_name.split() or [""])[0] if candidate else ""
    return UnsubscribeOut(first_name=first, unsubscribed=row.unsubscribed_at is not None)


def unsubscribe(session: Session, token: str) -> UnsubscribeOut:
    row = _by_token(session, token)
    if not row.unsubscribed_at:
        row.unsubscribed_at = utc_now()
        session.add(row)
        session.commit()
        log.info("talent pool unsubscribe candidate=%s", row.candidate_id)
    return unsubscribe_info(session, token)
