"""Scheduling an interview for a shortlisted candidate. The invitation itself is the LangGraph workflow
app/graphs/invitation_graph.py; this file starts it and passes the interviewer's clicks to it.

    schedule(...)            creates the interview with a private join link, then starts the invitation workflow
                             (it writes and checks the draft, then pauses for the interviewer)
    reschedule(...)          a new time; the workflow writes a new draft (the calendar event is updated when sent)
    rewrite(...)             "Write again with AI": the paused workflow writes a new draft
    send_invitation(...)     "Send email": the paused workflow sends the checked text with the calendar invite
    plan_times(...)          "Suggest times": a time for each shortlisted candidate inside working hours (nothing saved)
    write_template(...)      "Write the invitation": the AI writes ONE invitation for the whole shortlist (to check)
    schedule_many(...)       "Schedule and save invitations": schedule() for each candidate with the checked invitation
    send_all(...)            "Send all invitations": send_invitation() for every unsent draft of the job
    start_call(...)          the interviewer starts (or joins again) the video call: status live + a ticket
    end_call(...)            the interviewer ends the call for both: status ended
    candidate_ticket(...)    the candidate's ticket, only while the call is live
    session_out(...)         one interview for the page
    email_check()            the Settings button "Test email"

Draft first: nothing is sent by itself. The AI writes, code checks and puts in the link, a person sends.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core import config
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.ai.llm_client import llm_json
from app.features.interviews.schemas import (BulkOut, BulkProblem, PlanIn, PlanRowOut, ScheduleIn, SessionOut,
                                             TemplateText, TicketOut)
from app.features.interviews.services.invitation_service import (
    as_utc, email_check, interviewer_name, join_link, standard_text, template_facts, template_problems)
from app.graphs.invitation_prompts import INVITATION_TEMPLATE_PROMPT
from app.features.interviews.services.slot_service import WorkingHours, hours_problem, plan_slots
from app.features.interviews.services.video_service import make_ticket, video_problem
from app.features.jobs.models import Job
from app.features.screening.models import ShortlistEntry
from app.features.screening.services.shortlist_service import shortlist_rows
from app.features.system.models import WorkflowRun
from app.graphs.invitation_graph import answer, start_invitation

log = logging.getLogger("interviews")

MAX_DAYS_AHEAD = 365
__all__ = ["candidate_ticket", "email_check", "end_call", "plan_times", "reschedule", "rewrite", "schedule",
           "schedule_many", "send_all", "send_invitation", "session_out", "start_call"]


# Converts the start to UTC and checks it is in the future and within one year
def _check_time(start: datetime) -> datetime:
    start = start.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if start <= now:
        raise HTTPException(400, "The interview time must be in the future.")
    if start > now + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(400, "The interview time must be within one year.")
    return start


# Adds a WorkflowRun row (stage 'invitation') so the step shows in the workflow run log
def _log(session: Session, interview: InterviewSession, outcome: str) -> None:
    session.add(WorkflowRun(stage="invitation", subject_id=interview.candidate_id, outcome=outcome, seconds=0.0))


def _fresh(session: Session, interview: InterviewSession) -> InterviewSession:
    """The workflow saved with its own database session: read the interview again."""
    session.expire_all()
    return session.get(InterviewSession, interview.id)


# Creates the interview with a join token and room, then starts the invitation graph (start_invitation)
def schedule(session: Session, candidate_id: int, start: datetime, minutes: int, time_zone: str, by: str,
             template: dict | None = None) -> SessionOut:
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    if not session.exec(select(ShortlistEntry).where(ShortlistEntry.candidate_id == candidate_id)).first():
        raise HTTPException(400, "Only a shortlisted candidate can be invited. Put them on the shortlist first.")
    waiting = session.exec(select(InterviewSession).where(InterviewSession.candidate_id == candidate_id,
                                                          InterviewSession.status != "ended")).first()
    if waiting:
        raise HTTPException(409, "This candidate already has an interview. Open it to change the time or send the email.")

    interview = InterviewSession(candidate_id=candidate.id, job_id=candidate.job_id, scheduled_at=_check_time(start),
                                 duration_minutes=minutes, time_zone=time_zone,
                                 join_token=secrets.token_urlsafe(32),          # about 43 random characters
                                 room_name=f"interview-{secrets.token_hex(8)}", invite_email=candidate.email,
                                 created_by=by)
    session.add(interview)
    _log(session, interview, "scheduled")
    session.commit()
    session.refresh(interview)
    message = start_invitation(interview, interviewer_name(session, by), template)   # the workflow writes the draft
    log.info("interview scheduled candidate=%s session=%s", candidate.id, interview.id)
    return session_out(session, _fresh(session, interview), message)


# Saves a new time, raises calendar_sequence, and asks the paused graph for a new draft (answer)
def reschedule(session: Session, interview: InterviewSession, start: datetime, minutes: int, time_zone: str,
               by: str) -> SessionOut:
    if interview.status != "scheduled":
        raise HTTPException(400, "This interview has started or ended; its time cannot be changed.")
    interview.scheduled_at, interview.duration_minutes, interview.time_zone = _check_time(start), minutes, time_zone
    interview.calendar_sequence += 1                  # the candidate's calendar moves the same event
    _log(session, interview, "time changed")
    session.add(interview)
    session.commit()
    message = answer(interview, {"action": "write_again"}, interviewer_name(session, by))   # a draft with the new time
    return session_out(session, _fresh(session, interview),
                       "New time saved. " + message.replace("Check it, then click Send email.", "Send it so the candidate knows."))


# Resumes the paused invitation graph with 'write_again' so the AI writes a new draft (answer)
def rewrite(session: Session, interview: InterviewSession, by: str) -> SessionOut:
    # → resumes the paused invitation graph: write a new draft (invitation_graph)
    message = answer(interview, {"action": "write_again"}, interviewer_name(session, by))
    return session_out(session, _fresh(session, interview), message)


def send_invitation(session: Session, interview: InterviewSession, to: str, subject: str, body: str, by: str) -> SessionOut:
    """Only after the interviewer clicked Send: the workflow continues from ask_person to send_email."""
    if interview.status == "ended":
        raise HTTPException(400, "This interview has ended.")
    # → resumes the paused invitation graph at ask_person, which goes to send_email
    message = answer(interview, {"action": "send", "to": to, "subject": subject, "body": body},
                     interviewer_name(session, by))
    return session_out(session, _fresh(session, interview), message)


# ---------- many candidates at once: suggest times, schedule all, send all ----------

# The open interview (not ended) of a candidate, or None
def _open_interview(session: Session, candidate_id: int) -> InterviewSession | None:
    return session.exec(select(InterviewSession).where(InterviewSession.candidate_id == candidate_id,
                                                       InterviewSession.status != "ended")).first()


def plan_times(session: Session, body: PlanIn, by: str) -> list[PlanRowOut]:
    """A suggested time for every shortlisted candidate, highest score first. Candidates who already have an
    interview keep it; the interviewer's other open interviews are never overlapped. The first suggestion comes after
    the end of the interviewer's last interview, or at "Start at" when it is given. Nothing is saved."""
    job = session.get(Job, body.job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    hours = WorkingHours(body.day_start, body.day_end, None if body.skip_lunch else body.lunch_start,
                         None if body.skip_lunch else body.lunch_end)
    problem = hours_problem(hours, body.duration_minutes)
    if problem:
        raise HTTPException(400, problem)
    mine = session.exec(select(InterviewSession).where(InterviewSession.created_by == by,
                                                       InterviewSession.status != "ended")).all()
    busy = [(as_utc(i.scheduled_at), as_utc(i.scheduled_at) + timedelta(minutes=i.duration_minutes)) for i in mine]
    if body.start_at:                                 # "Start at": the first day starts at that time
        not_before = datetime.combine(body.first_day, body.start_at, tzinfo=ZoneInfo(body.time_zone))
    else:                                             # default: after the end of your last interview (never earlier)
        not_before = max((end for _, end in busy), default=None)
    rows = shortlist_rows(session, job)
    waiting = [row for row in rows if not _open_interview(session, row.candidate_id)]
    starts = plan_slots(len(waiting), body.first_day, body.duration_minutes, body.time_zone, hours, busy,
                        not_before=not_before)
    planned = dict(zip([row.candidate_id for row in waiting], starts))
    answer = []
    for row in rows:
        existing = _open_interview(session, row.candidate_id)
        answer.append(PlanRowOut(candidate_id=row.candidate_id, full_name=row.full_name or f"Candidate {row.number}",
                                 weighted_score=row.weighted_score, session_id=existing.id if existing else None,
                                 scheduled_at=as_utc(existing.scheduled_at) if existing else planned.get(row.candidate_id)))
    return answer


def write_template(session: Session, job_id: int, minutes: int, by: str) -> TemplateText:
    """ONE invitation for the whole shortlist, for the interviewer to check: the AI writes it with {candidate_name},
    {date} and {time} as placeholders. If the AI fails or breaks a rule, the standard text is used. Nothing is saved."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    facts = template_facts(job.title, minutes, interviewer_name(session, by))
    answer = llm_json(INVITATION_TEMPLATE_PROMPT, facts)        # → Gemini: one email, never a real name or address
    if isinstance(answer, dict):
        subject, body = str(answer.get("subject") or "").strip()[:200], str(answer.get("body") or "").strip()[:7000]
        problems = template_problems(subject, body)
        if not problems:
            return TemplateText(subject=subject, body=body, message="The AI wrote the invitation. Check it before scheduling.")
        message = "The AI's email did not pass the check (" + "; ".join(problems) + "), so the standard text is used."
    else:
        message = "The AI did not answer, so the standard text is used."
    subject, body = standard_text(facts)
    return TemplateText(subject=subject, body=body, message=message)


def schedule_many(session: Session, items: list[ScheduleIn], by: str, template: TemplateText | None = None) -> BulkOut:
    """schedule() for each candidate, one after another: each gets its own link and room. With a template (checked by
    the interviewer) each draft is that text filled in for the candidate, with no AI call; without one, the AI writes
    each draft. One problem (e.g. a time in the past) does not stop the others; nothing is sent."""
    chosen = None
    if template:
        problems = template_problems(template.subject, template.body)
        if problems:
            raise HTTPException(400, "The invitation cannot be used: " + "; ".join(problems) + ".")
        chosen = {"subject": template.subject, "body": template.body}
    done, problems = [], []
    for item in items:
        try:
            done.append(schedule(session, item.candidate_id, item.scheduled_at, item.duration_minutes, item.time_zone, by,
                                 chosen))
        except HTTPException as problem:
            session.rollback()
            candidate = session.get(Candidate, item.candidate_id)
            problems.append(BulkProblem(candidate_id=item.candidate_id, full_name=candidate.full_name if candidate else "",
                                        reason=str(problem.detail)))
    message = f"{len(done)} interview(s) scheduled with their invitation saved. Click Send all invitations to send them."
    return BulkOut(sessions=done, problems=problems, message=message + (f" {len(problems)} could not be scheduled." if problems else ""))


def send_all(session: Session, job_id: int, by: str) -> BulkOut:
    """Only after the interviewer clicked "Send all" and said Yes: every scheduled interview of the job whose invitation
    is not sent yet is sent as it is now (the same path as the Send button: the workflow and the email MCP server)."""
    rows = session.exec(select(InterviewSession).where(InterviewSession.job_id == job_id,
                                                       InterviewSession.status == "scheduled",
                                                       InterviewSession.invitation_status != "sent")
                        .order_by(InterviewSession.scheduled_at)).all()
    done, problems = [], []
    for interview in rows:
        result = send_invitation(session, interview, interview.invite_email, interview.invitation_subject,
                                 interview.invitation_body, by)
        done.append(result)
        if result.invitation_status != "sent":
            problems.append(BulkProblem(candidate_id=result.candidate_id, full_name=result.candidate_name,
                                        reason=_not_sent_reason(result.invitation_status)))
    sent = len(done) - len(problems)
    message = f"{sent} invitation(s) sent." if rows else "There is no unsent invitation."
    return BulkOut(sessions=done, problems=problems, message=message + (f" {len(problems)} not sent." if problems else ""))


# The invitation status in plain words, for an invitation that was not sent
def _not_sent_reason(status: str) -> str:
    if status == "no_email":
        return "No email address."
    if status == "not_sent":
        return "Email is not set up (SMTP in .env)."
    return status.removeprefix("failed: ") or "Not sent."


# Builds the SessionOut answer for the page: candidate, job, time, join link, invitation, call times
def session_out(session: Session, interview: InterviewSession, message: str = "") -> SessionOut:
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    return SessionOut(id=interview.id, candidate_id=interview.candidate_id, job_id=interview.job_id,
                      candidate_name=candidate.full_name if candidate else "", job_title=job.title if job else "",
                      scheduled_at=as_utc(interview.scheduled_at), duration_minutes=interview.duration_minutes,
                      time_zone=interview.time_zone, join_link=join_link(interview), status=interview.status,
                      invite_email=interview.invite_email, invitation_subject=interview.invitation_subject,
                      invitation_body=interview.invitation_body, invitation_status=interview.invitation_status,
                      sent_at=as_utc(interview.sent_at) if interview.sent_at else None, created_by=interview.created_by,
                      created_at=as_utc(interview.created_at), message=message,
                      started_at=_maybe_utc(interview.started_at),
                      candidate_joined_at=_maybe_utc(interview.candidate_joined_at),
                      ended_at=_maybe_utc(interview.ended_at))


# Returns the time marked as UTC, or None when there is no time
def _maybe_utc(moment):
    return as_utc(moment) if moment else None


# ---------- the video call ----------

def start_call(session: Session, interview: InterviewSession, by: str) -> TicketOut:
    """Starts the call (status live) or joins it again. Any time after scheduling, so a demo can start early.
    The candidate can join only while it is live."""
    if interview.status == "ended":
        raise HTTPException(400, "This interview has ended. Schedule a new one to talk again.")
    problem = video_problem()
    if problem:
        raise HTTPException(503, problem + ". Add the LiveKit keys and restart the backend.")
    if interview.status != "live":
        interview.status, interview.started_at = "live", datetime.now(timezone.utc)
        _log(session, interview, "call started")
        session.add(interview)
        session.commit()
        session.refresh(interview)
        log.info("call started session=%s", interview.id)
    # → signs a LiveKit ticket for this one room (video_service.make_ticket)
    ticket = make_ticket(interview.room_name, "interviewer", interviewer_name(session, by))
    return TicketOut(server_url=config.LIVEKIT_URL, ticket=ticket, room_name=interview.room_name,
                     identity="interviewer", session=session_out(session, interview))


def end_call(session: Session, interview: InterviewSession) -> SessionOut:
    """Ends the call for both. The candidate's page sees "ended" and leaves; the link cannot be used again."""
    if interview.status != "ended":
        interview.status, interview.ended_at = "ended", datetime.now(timezone.utc)
        _log(session, interview, "call ended")
        session.add(interview)
        session.commit()
        session.refresh(interview)
        log.info("call ended session=%s", interview.id)
    return session_out(session, interview, "The interview has ended.")


def candidate_ticket(session: Session, interview: InterviewSession, name: str) -> TicketOut:
    """The candidate's ticket: only while the interviewer has the call open (not before, not after)."""
    if interview.status == "scheduled":
        raise HTTPException(409, "The interviewer has not started the interview yet. Please wait on this page.")
    if interview.status == "ended":
        raise HTTPException(409, "This interview has ended.")
    problem = video_problem()
    if problem:
        raise HTTPException(503, "The video call is not available right now. Please tell the interviewer.")
    if not interview.candidate_joined_at:
        interview.candidate_joined_at = datetime.now(timezone.utc)
        _log(session, interview, "candidate joined")
        session.add(interview)
        session.commit()
    # → candidate's LiveKit ticket for the same room (video_service.make_ticket)
    return TicketOut(server_url=config.LIVEKIT_URL, ticket=make_ticket(interview.room_name, "candidate", name.strip()),
                     room_name=interview.room_name, identity="candidate")
