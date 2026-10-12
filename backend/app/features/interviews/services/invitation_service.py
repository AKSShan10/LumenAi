"""The parts of the invitation that the invitation workflow (app/graphs/invitation_graph.py) uses. Plain code, no AI.

    join_link(interview)          APP_URL/join/<join_token>: the candidate's private link
    when_text(interview)          ("Tuesday, 20 October 2026", "3:00 PM (Asia/Dhaka, GMT+06)") for the email
    with_link(body, link)         puts the real link where the AI wrote {join_link}; adds it if it is missing
    draft_problems(...)           what is wrong with a draft (the check step): no link, an invented link, too long ...
    standard_text(...)            a plain invitation, used when the AI cannot write a good one
    calendar_for(...)             the calendar invite (.ics) for the email
    deliver(...)                  sends through the email MCP server (or directly with EMAIL_TRANSPORT=smtp)
"""
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.core import config
from app.features.auth.models import User
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.interviews.services import smtp_service
from app.features.interviews.services.calendar_service import calendar_invite
from app.features.jobs.models import Job
from app.mcp_servers.client import McpError, call_tool

EMAIL_SERVER = "app.mcp_servers.email_server"
PLACEHOLDER = "{join_link}"
MAX_WORDS = 300                  # the AI is asked for 220 words at most; a little more is still fine


def join_link(interview: InterviewSession) -> str:
    return f"{config.APP_URL}/join/{interview.join_token}"


def as_utc(moment: datetime) -> datetime:
    """SQLite gives times back without a time zone; they are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def when_text(interview: InterviewSession) -> tuple[str, str]:
    """The date and the time in the interviewer's time zone, written for the reader."""
    local = as_utc(interview.scheduled_at).astimezone(ZoneInfo(interview.time_zone))
    offset = local.strftime("%z")
    hours = f"GMT{offset[:3]}" + (f":{offset[3:]}" if offset[3:] != "00" else "")
    clock = local.strftime("%I:%M %p").lstrip("0")
    return local.strftime("%A, %d %B %Y").replace(" 0", " "), f"{clock} ({interview.time_zone}, {hours})"


def interviewer_name(session: Session, email: str) -> str:
    user = session.exec(select(User).where(User.email == email)).first()
    return (user.full_name if user else "") or "The interviewer"      # never an email address in the text


def email_facts(session: Session, interview: InterviewSession, interviewer: str) -> dict:
    """What the AI gets to write the email. Never the candidate's email address."""
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    day, clock = when_text(interview)
    return {"candidate_name": candidate.full_name or "candidate", "job_title": job.title, "date": day, "time": clock,
            "length_minutes": interview.duration_minutes, "interviewer_name": interviewer}


def with_link(body: str, link: str) -> str:
    """The real link instead of the placeholder. If the link is missing (the AI or a person removed it), it is added."""
    body = body.replace(PLACEHOLDER, link)
    if link not in body:
        body = body.rstrip() + f"\n\nJoin the interview with your personal link:\n{link}"
    return body


def draft_problems(subject: str, body: str, facts: dict) -> list[str]:
    """The check step: plain rules every draft must pass, before a person sees it."""
    problems = []
    if not subject.strip() or not body.strip():
        problems.append("the subject or the text is empty")
    if PLACEHOLDER not in body:
        problems.append("the {join_link} placeholder is missing")
    if re.search(r"https?://|www\.", body):
        problems.append("the text has a web address of its own (only {join_link} may stand for the link)")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body):
        problems.append("the text has an email address")
    if facts["date"] not in body:
        problems.append("the interview date is not written as given")
    if len(body.split()) > MAX_WORDS:
        problems.append(f"the text is too long ({len(body.split())} words)")
    return problems


def standard_text(facts: dict) -> tuple[str, str]:
    """(subject, body): a plain invitation, used when the AI cannot write one that passes the check."""
    body = (f"Dear {facts['candidate_name']},\n\nThank you for applying for the {facts['job_title']} position. We would "
            f"like to invite you to an online video interview.\n\nDate: {facts['date']}\nTime: {facts['time']}\n"
            f"Length: about {facts['length_minutes']} minutes\n\nJoin the interview with your personal link:\n"
            f"{PLACEHOLDER}\n\nA calendar invite is attached. Please use a computer or phone with a camera, a microphone "
            "and a stable internet connection, in a quiet place. The interview is transcribed and analysed by AI to "
            "help the interviewer; a person makes every decision.\n\nIf the time does not suit you, please reply to "
            f"this email.\n\nKind regards,\n{facts['interviewer_name']}\nHiring team")
    return f"Interview invitation: {facts['job_title']}", body


def calendar_for(session: Session, interview: InterviewSession, to: str) -> str:
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    link = join_link(interview)
    return calendar_invite(uid=f"interview-{interview.id}-{interview.join_token[:12]}@lumenai",
                           start=as_utc(interview.scheduled_at), minutes=interview.duration_minutes,
                           title=f"Interview: {job.title}",
                           description=f"Online video interview for {job.title}.\nJoin with your personal link: {link}",
                           link=link, organizer=config.SMTP_FROM, attendee=to, attendee_name=candidate.full_name,
                           sequence=interview.calendar_sequence)


def deliver(to: str, subject: str, body: str, calendar: str) -> dict:
    """Through the email MCP server (default), or directly with EMAIL_TRANSPORT=smtp. Returns {"ok", "error"}."""
    if config.EMAIL_TRANSPORT != "mcp":
        return smtp_service.send_email(to, subject, body, calendar)
    try:
        return json.loads(call_tool(EMAIL_SERVER, "send_email", {"to": to, "subject": subject, "body": body,
                                                                 "calendar": calendar}))
    except (McpError, ValueError) as problem:
        return {"ok": False, "error": f"the email tool did not answer ({problem})"}


def email_check() -> dict:
    """The Settings button: through the MCP server, like the real sending. Sends nothing."""
    if config.EMAIL_TRANSPORT != "mcp":
        return smtp_service.check_email_settings()
    try:
        return json.loads(call_tool(EMAIL_SERVER, "check_email_settings"))
    except (McpError, ValueError) as problem:
        return {"ok": False, "message": f"The email tool did not answer ({problem})"}
