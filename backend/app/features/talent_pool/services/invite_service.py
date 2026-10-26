"""Invitations to a new job for pool candidates. The AI drafts, the interviewer checks and clicks Send.

    drafts(session, job, body, by)        one checked draft per chosen person (graphs/talent_invite_graph.py);
                                          also "Write again" for one person, with a wish (always formal); then the
                                          draft on the page is improved, e.g. made shorter, instead of a new one
    send(session, job, invites, by)       sends the checked emails (SMTP) and records them; refuses anyone who
                                          unsubscribed, expired or already applied
Code adds the apply link and the unsubscribe link below every email, so they are never missing.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session

from app.core import config
from app.features.candidates.models import Candidate
from app.features.interviews.services.invitation_service import interviewer_name
from app.features.interviews.services.smtp_service import send_email
from app.features.jobs.models import Job
from app.features.talent_pool.models import TalentInvite, TalentPoolEntry
from app.features.talent_pool.schemas import DraftIn, InviteDraft, InviteResult
from app.features.talent_pool.services.pool_service import _applied, matches, state
from app.graphs.talent_invite_graph import draft_invite, with_job_title

log = logging.getLogger("talent_pool")


# Below every invitation: where to apply (the job's Google Form) and how to stop these emails
def footer(job: Job, entry: TalentPoolEntry) -> str:
    lines = [f"Apply here: {job.google_form_link}"] if job.google_form_link else []
    lines.append(f"If you do not want emails about future openings: {config.APP_URL}/unsubscribe/{entry.unsubscribe_token}")
    return "\n\n---\n" + "\n".join(lines)


def drafts(session: Session, job: Job, body: DraftIn, by: str) -> list[InviteDraft]:
    """Only people who fit this job can be drafted (code decided who fits; the page's filters do not matter here)."""
    fitting = {m.pool_id: m for m in matches(session, job, min_match=0)}
    signature = f"\n\nBest regards,\n{interviewer_name(session, by)}"
    previous = {}
    if body.previous_body.strip():                                      # "Write again": improve the draft on the page
        if len(set(body.pool_ids)) != 1:
            raise HTTPException(409, "Write again works for one person at a time.")
        text = body.previous_body.strip()
        text = text.replace(signature.strip(), "").strip()               # the signature is added again below
        previous = {"subject": body.previous_subject.strip(), "body": text}
    result = []
    for pool_id in dict.fromkeys(body.pool_ids):
        match = fitting.get(pool_id)
        if not match:
            raise HTTPException(409, "Someone you chose is not in the list of past candidates for this job any more.")
        draft = draft_invite(pool_id, job.id, body.instruction.strip(), previous)   # → the LangGraph workflow
        candidate, entry = session.get(Candidate, match.candidate_id), session.get(TalentPoolEntry, pool_id)
        result.append(InviteDraft(pool_id=pool_id, name=candidate.full_name, email=candidate.email,
                                  subject=draft["subject"][:200], body=(draft["body"] + signature)[:4000],
                                  footer=footer(job, entry)))
    return result


def send(session: Session, job: Job, invites: list[InviteDraft], by: str) -> list[InviteResult]:
    results = []
    for invite in invites:
        entry = session.get(TalentPoolEntry, invite.pool_id)
        candidate = session.get(Candidate, entry.candidate_id) if entry else None
        if not entry or not candidate:
            results.append(InviteResult(pool_id=invite.pool_id, name=invite.name, ok=False, error="not in the pool"))
            continue
        problem = {"unsubscribed": "this person unsubscribed",
                   "expired": "this person's time in the pool has ended"}.get(state(entry), "")
        if not problem and _applied(session, candidate.email, job.id):
            problem = "this person already applied to this job"
        if problem:
            results.append(InviteResult(pool_id=entry.id, name=candidate.full_name, ok=False, error=problem))
            continue
        # → SMTP: always to the saved address (never one typed on the page), the job title in the subject (also when
        # the interviewer removed it), and the links added by code
        subject = with_job_title(invite.subject, job.title)
        sent = send_email(candidate.email, subject, invite.body.strip() + footer(job, entry))
        if sent["ok"]:
            session.add(TalentInvite(pool_id=entry.id, job_id=job.id, subject=subject,
                                     body=invite.body.strip(), sent_by=by))
            session.commit()
        log.info("talent invite job=%s candidate=%s ok=%s", job.id, candidate.id, sent["ok"])
        results.append(InviteResult(pool_id=entry.id, name=candidate.full_name, ok=sent["ok"], error=sent["error"]))
    return results
