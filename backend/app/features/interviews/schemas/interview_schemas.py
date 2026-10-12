"""Request and response bodies for interviews."""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class _When(BaseModel):
    """scheduled_at: the start with its time offset, e.g. 2026-10-20T15:00:00+06:00 (the browser sends UTC "...Z").
    time_zone: the interviewer's time zone name, e.g. Asia/Dhaka, used to write the time in the email."""
    scheduled_at: datetime
    duration_minutes: int = Field(default=45, ge=15, le=180)
    time_zone: str = Field(default="UTC", max_length=60)

    @field_validator("scheduled_at")
    @classmethod
    def has_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("The time needs a time zone offset, for example 2026-10-20T09:00:00Z")
        return value

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
    message: str = ""                # what just happened, in plain words (after scheduling, writing or sending)


class JoinInfoOut(BaseModel):
    """What the candidate's page may show: nothing about scores, notes or other candidates."""
    job_title: str
    candidate_name: str
    scheduled_at: datetime
    duration_minutes: int
    status: str
