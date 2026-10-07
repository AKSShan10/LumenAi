"""Table `job`: one job opening with its requirements and its description."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = Field(default="", sa_column=Column(Text))   # written by the AI, edited by the interviewer
    required_skills: list = Field(default_factory=list, sa_column=Column(JSON))
    preferred_skills: list = Field(default_factory=list, sa_column=Column(JSON))
    min_years: int = 0
    qualifications: str = ""                          # e.g. "BSc in CSE or similar"
    prompt: str = Field(default="", sa_column=Column(Text))        # the short text the interviewer typed for the AI
    status: str = "draft"                             # draft | approved; editing an approved job makes it a draft again
    approved_at: Optional[datetime] = None
    response_sheet_url: str = ""                      # the response sheet of this job's Google Form (applications)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
