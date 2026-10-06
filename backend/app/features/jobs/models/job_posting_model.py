"""Table `job_posting`: one try to post an approved job to the Telegram channel, and how it ended."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class JobPosting(SQLModel, table=True):
    __tablename__ = "job_posting"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    channel: str = "telegram"
    text: str = Field(sa_column=Column(Text))         # the post as the interviewer approved it
    apply_url: str = ""                               # the Google Form the candidates fill in
    status: str = "posted"                            # posted | failed
    error: str = Field(default="", sa_column=Column(Text))
    message_id: int = 0                               # Telegram's number of the message
    message_link: str = ""                            # link to the post (public channels only)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
