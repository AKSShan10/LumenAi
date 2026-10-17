"""Request and response bodies for interviews."""
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.features.candidates.schemas import CandidateOut
from app.features.screening.schemas import ScreeningRowOut


class _When(BaseModel):
    """scheduled_at: the start with its time offset, e.g. 2026-10-20T15:00:00+06:00 (the browser sends UTC "...Z").
    time_zone: the interviewer's time zone name, e.g. Asia/Dhaka, used to write the time in the email."""
    scheduled_at: datetime
    duration_minutes: int = Field(default=45, ge=15, le=180)
    time_zone: str = Field(default="UTC", max_length=60)

    # Rejects a scheduled_at time that has no time zone offset
    @field_validator("scheduled_at")
    @classmethod
    def has_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("The time needs a time zone offset, for example 2026-10-20T09:00:00Z")
        return value

    # Rejects a time zone name that Python's ZoneInfo does not know, like 'Mars/Base'
    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown time zone: {value}")
        return value


class ScheduleIn(_When):
    candidate_id: int


class RescheduleIn(_When):
    pass


class PlanIn(BaseModel):
    """Settings for "Suggest times": the shortlist of the job gets times one after another inside working hours."""
    job_id: int
    first_day: date                                  # e.g. 2026-10-19
    duration_minutes: int = Field(default=45, ge=15, le=180)
    time_zone: str = Field(default="UTC", max_length=60)
    day_start: time = time(8, 0)
    day_end: time = time(17, 0)
    lunch_start: time = time(12, 30)
    lunch_end: time = time(13, 30)
    start_at: Optional[time] = None                  # the first day starts here; None = after your last interview
    skip_lunch: bool = False                         # True = no lunch break: interviews may run through lunch time

    # Rejects a time zone name that Python's ZoneInfo does not know
    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        return _When.known_zone(value)


class PlanRowOut(BaseModel):
    """One shortlisted candidate with a suggested time, or the time of the interview they already have."""
    candidate_id: int
    full_name: str
    weighted_score: Optional[float] = None
    scheduled_at: Optional[datetime] = None          # None = no free time found
    session_id: Optional[int] = None                 # set when the candidate already has an interview (kept as it is)


class TemplateIn(BaseModel):
    """ "Write the invitation": the AI writes ONE invitation for the shortlist of this job."""
    job_id: int
    duration_minutes: int = Field(default=45, ge=15, le=180)


class TemplateText(BaseModel):
    """One invitation for many candidates: {candidate_name}, {date}, {time}, {length_minutes}, {interviewer_name} and
    {join_link} are filled in for each candidate by code."""
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    message: str = ""


class ScheduleManyIn(BaseModel):
    """ "Schedule and save invitations": one time per candidate, the same length and time zone for all.
    template = the invitation the interviewer checked (no AI call per candidate); None = the AI writes each one."""
    items: list[ScheduleIn] = Field(min_length=1, max_length=50)
    template: Optional[TemplateText] = None


class InvitationIn(BaseModel):
    """The invitation as the interviewer edited it, to send now."""
    to: str = Field(default="", max_length=200)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)


class SessionOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    candidate_name: str
    job_title: str
    scheduled_at: datetime
    duration_minutes: int
    time_zone: str
    join_link: str
    status: str
    invite_email: str
    invitation_subject: str
    invitation_body: str
    invitation_status: str
    sent_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    candidate_joined_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    analysis_status: str = "not_started"   # the Q&A analysis: not_started | running | done | failed
    analysis_error: str = ""               # why the analysis failed, in plain words
    interview_score: Optional[float] = None  # from the Q&A analysis (0-100), shown in the Interviews list
    message: str = ""                # what just happened, in plain words (after scheduling, writing or sending)


class JoinInfoOut(BaseModel):
    """What the candidate's page may show: nothing about scores, notes or other candidates."""
    job_title: str
    candidate_name: str
    scheduled_at: datetime
    duration_minutes: int
    status: str


class JoinTicketIn(BaseModel):
    """The candidate's name, shown in the call."""
    name: str = Field(min_length=1, max_length=60)


class TicketOut(BaseModel):
    """What a browser needs to join the call: the LiveKit server, a signed ticket for one room, and who it is."""
    server_url: str
    ticket: str
    room_name: str
    identity: str                    # interviewer | candidate
    session: Optional[SessionOut] = None    # the interview as it is now (interviewer only)


class ChatIn(BaseModel):
    """One chat message in the call: text, and links are simply part of the text."""
    text: str = Field(min_length=1, max_length=1000)


class CallMessageOut(BaseModel):
    id: int
    sender: str                      # interviewer | candidate
    sender_name: str                 # the name shown in the chat
    text: str
    sent_at: datetime


class ProfileOut(BaseModel):
    """The candidate's profile for the interviewer during the call. Never sent to the candidate."""
    candidate: CandidateOut          # name, email, phone, where they applied from, CV file
    job_title: str
    weights: dict                    # {"skills": 40, "experience": 35, "qualifications": 25}
    screening: Optional[ScreeningRowOut] = None   # None = the CV was not screened
    jobs: list[dict] = []            # from the CV, as the AI read it: [{"title", "company", "years"}], latest first
    degrees: list[dict] = []         # from the CV: [{"degree", "institute"}]


class BulkProblem(BaseModel):
    candidate_id: int
    full_name: str
    reason: str


class BulkOut(BaseModel):
    """The answer of "Schedule all" and "Send all": what worked, and what did not, in plain words."""
    sessions: list[SessionOut] = []
    problems: list[BulkProblem] = []
    message: str = ""
