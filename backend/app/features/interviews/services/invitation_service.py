"""Everything the invitation email needs except the AI call and the sending. Plain code, no AI.

The invitation workflow (graphs/invitation_graph.py) uses these in this order:

    1. Facts for the AI      email_facts()                 name, job, date, time ... (never the email address)
    2. Check the AI's draft  draft_problems()              rules every draft must pass before a person sees it
                             standard_text()               a plain invitation when the AI's draft keeps failing
    3. Finish the text       join_link(), with_link()      the candidate's private link instead of {join_link}
                             subject_with_time()           the date and time added to the subject
    4. The calendar invite   calendar_for()                the .ics invite that goes with the email
    5. "Schedule all"        template_facts(), fill_template(), template_problems()   one checked text for many

Small helpers used in several places: as_utc(), interviewer_name().
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.core import config
from app.features.auth.models import User
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.interviews.services.calendar_service import calendar_invite
from app.features.jobs.models import Job

PLACEHOLDER = "{join_link}"      # the AI writes this; code puts the real link there (the AI never sees the link)
MAX_WORDS = 300                  # the AI is asked for 220 words at most; a little more is still fine


# ---------- small helpers ----------

def as_utc(moment: datetime) -> datetime:
    """SQLite gives times back without a time zone; they are UTC, so UTC is added."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def interviewer_name(session: Session, email: str) -> str:
    """The interviewer's full name for the email signature, or "The interviewer" (never an email address)."""
    user = session.exec(select(User).where(User.email == email)).first()
    return (user.full_name if user else "") or "The interviewer"


# ---------- 1. facts for the AI ----------

def email_facts(session: Session, interview: InterviewSession, interviewer: str) -> dict:
    """What the AI gets to write the email. Never the candidate's email address.

    Example: {"candidate_name": "Karima Akter", "job_title": "Backend Developer",
              "date": "Tuesday, 20 October 2026", "time": "3:00 PM (Asia/Dhaka, GMT+06)",
              "length_minutes": 45, "interviewer_name": "Shan"}
    """
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    # the interview time in the interviewer's time zone, written for a reader
    local = as_utc(interview.scheduled_at).astimezone(ZoneInfo(interview.time_zone))
    offset = local.strftime("%z")                                          # e.g. "+0600"
    hours = f"GMT{offset[:3]}" + (f":{offset[3:]}" if offset[3:] != "00" else "")   # "+0600" -> "GMT+06"
    day = local.strftime("%A, %d %B %Y").replace(" 0", " ")               # "Tuesday, 20 October 2026" (no leading 0)
    clock = local.strftime("%I:%M %p").lstrip("0")                        # "3:00 PM"
    return {"candidate_name": candidate.full_name or "candidate", "job_title": job.title, "date": day,
            "time": f"{clock} ({interview.time_zone}, {hours})", "length_minutes": interview.duration_minutes,
            "interviewer_name": interviewer}


# ---------- 2. check the AI's draft ----------

def draft_problems(subject: str, body: str, facts: dict) -> list[str]:
    """The check step: plain rules every draft must pass, before a person sees it. [] = fine."""
    problems = []
    if not subject.strip() or not body.strip():
        problems.append("the subject or the text is empty")
    if PLACEHOLDER not in body:
        problems.append("the {join_link} placeholder is missing")
    if re.search(r"https?://|www\.", body):                     # a web address the AI made up
        problems.append("the text has a web address of its own (only {join_link} may stand for the link)")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body):             # something that looks like name@domain.com
        problems.append("the text has an email address")
    if facts["date"] not in body:                               # the AI must copy the date, never change it
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
            "and a stable internet connection, in a quiet place.\n\nIf the time does not suit you, please reply to "
            f"this email.\n\nKind regards,\n{facts['interviewer_name']}\nHiring team")
    return f"Interview invitation: {facts['job_title']}", body


# ---------- 3. finish the text ----------

def join_link(interview: InterviewSession) -> str:
    """The candidate's private link, e.g. https://<APP_URL>/join/<join_token> (APP_URL comes from .env)."""
    return f"{config.APP_URL}/join/{interview.join_token}"


def with_link(body: str, link: str) -> str:
    """Puts the real link where the AI wrote {join_link}. If the link is missing (the AI or a person removed it),
    it is added at the end, so the candidate always gets it."""
    body = body.replace(PLACEHOLDER, link)
    if link not in body:
        body = body.rstrip() + f"\n\nJoin the interview with your personal link:\n{link}"
    return body


def subject_with_time(subject: str, interview: InterviewSession) -> str:
    """Adds the interview's date and time to the subject ("... - 15 Oct 2026, 10:00 AM"), so mail apps such as Gmail
    start a new thread for a new interview or a new time instead of putting it under the old email."""
    local = as_utc(interview.scheduled_at).astimezone(ZoneInfo(interview.time_zone))
    when = f"{local.day} {local:%b %Y}, " + local.strftime("%I:%M %p").lstrip("0")    # 15 Oct 2026, 10:00 AM
    subject = subject.strip()
    if when in subject:                               # already there: never twice
        return subject
    return f"{subject} - {when}" if subject else when


# ---------- 4. the calendar invite ----------

def calendar_for(session: Session, interview: InterviewSession, to: str) -> str:
    """The .ics invite for this interview (calendar_service.calendar_invite); sent with the email."""
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    link = join_link(interview)
    return calendar_invite(uid=f"interview-{interview.id}-{interview.join_token[:12]}@lumenai",   # same id every time
                           start=as_utc(interview.scheduled_at), minutes=interview.duration_minutes,
                           title=f"Interview: {job.title}",
                           description=f"Online video interview for {job.title}.\nJoin with your personal link: {link}",
                           link=link, organizer=config.SMTP_FROM, attendee=to, attendee_name=candidate.full_name,
                           sequence=interview.calendar_sequence)   # +1 after a new time: the calendar moves the event


# ---------- 5. "Schedule all": one checked text for many candidates ----------

# The placeholders of a template, and the fact each one is filled with
TEMPLATE_FIELDS = {"{candidate_name}": "candidate_name", "{date}": "date", "{time}": "time",
                   "{length_minutes}": "length_minutes", "{interviewer_name}": "interviewer_name"}


def template_facts(job_title: str, minutes: int, interviewer: str) -> dict:
    """The facts for writing ONE invitation for many candidates: the name, date and time stay placeholders."""
    return {"candidate_name": "{candidate_name}", "job_title": job_title, "date": "{date}", "time": "{time}",
            "length_minutes": minutes, "interviewer_name": interviewer}


def fill_template(text: str, facts: dict) -> str:
    """One candidate's text from the template: {candidate_name}, {date} ... replaced by their facts.
    {join_link} stays: save_draft puts in the real private link."""
    for placeholder, key in TEMPLATE_FIELDS.items():
        text = text.replace(placeholder, str(facts[key]))
    return text


def template_problems(subject: str, body: str) -> list[str]:
    """The same rules as draft_problems, for a template checked by the interviewer before it is used for everyone."""
    problems = draft_problems(subject, body, {"date": "{date}"})
    return [p.replace("the interview date is not written as given", "the {date} placeholder is missing") for p in problems]
