"""Table `interview_session`: one scheduled video interview of a shortlisted candidate, with its invitation."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class InterviewSession(SQLModel, table=True):
    """The candidate opens the call with the private link APP_URL/join/<join_token> from the invitation."""
    __tablename__ = "interview_session"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True)
    job_id: int = Field(index=True)
    scheduled_at: datetime                            # when the interview starts (UTC)
    duration_minutes: int = 45
    time_zone: str = "UTC"                            # the interviewer's time zone, e.g. Asia/Dhaka (for the email text)
    join_token: str = Field(index=True, unique=True)  # long random text: the candidate's private link
    room_name: str = Field(index=True, unique=True)   # the name of the video room (used by the call, F6)
    status: str = "scheduled"                         # scheduled | live | ended
    calendar_sequence: int = 0                        # +1 when the time changes, so calendars update the same event
    invite_email: str = ""                            # where the invitation goes (from the application, can be edited)
    invitation_subject: str = ""
    invitation_body: str = Field(default="", sa_column=Column(Text))
    # "" = draft, not sent yet | sent | not_sent (no SMTP set up) | no_email | failed: <reason in plain words>
    invitation_status: str = ""
    sent_at: Optional[datetime] = None
    created_by: str = ""                              # the email of the interviewer who scheduled it
    # The session record of the video call
    started_at: Optional[datetime] = None             # the interviewer started the call (status live)
    candidate_joined_at: Optional[datetime] = None    # the candidate first joined the call
    ended_at: Optional[datetime] = None               # the call was ended (status ended)
    # F7 identity check of the person in the call: {"result", "similarity", "better_match", "message", "checked_at",
    # "decision": confirmed | rejected | "", "decided_by", "decided_at"}; {} = not checked. The camera picture is never saved.
    identity: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
