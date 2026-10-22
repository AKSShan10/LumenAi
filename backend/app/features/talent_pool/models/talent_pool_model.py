"""Tables `talent_pool` and `talent_invite` (innovation feature).

    talent_pool     a past candidate the interviewer kept for future jobs (one row per candidate)
                    status: strong (strong candidate, not selected) | other_role (good fit for another role)
                    keep_until: after this date the person is no longer suggested (POOL_KEEP_DAYS in .env)
                    unsubscribe_token: the private part of the "no more emails" link; unsubscribed_at = they used it
    talent_invite   one invitation email sent to a pool candidate for a new job
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class TalentPoolEntry(SQLModel, table=True):
    __tablename__ = "talent_pool"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, unique=True)  # the application the person is kept from
    status: str = "strong"                            # strong | other_role
    note: str = Field(default="", sa_column=Column(Text))
    added_by: str = ""                                # the interviewer's email
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    keep_until: datetime                              # no longer suggested after this date
    unsubscribe_token: str = Field(index=True, unique=True)
    unsubscribed_at: Optional[datetime] = None        # the person asked for no more emails


class TalentInvite(SQLModel, table=True):
    __tablename__ = "talent_invite"
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(index=True)                  # the talent_pool row
    job_id: int = Field(index=True)                   # the new job they were invited to
    subject: str = ""
    body: str = Field(default="", sa_column=Column(Text))   # the text as the interviewer sent it
    sent_by: str = ""
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
