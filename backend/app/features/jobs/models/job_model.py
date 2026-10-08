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
    sheet_checkpoint_row: int = 1                     # the last row of that sheet that is finished (row 1 = the titles)
    # How much each part of the CV counts in the weighted score (F4). Set by the interviewer; they add up to 100.
    weight_skills: int = 50
    weight_experience: int = 30
    weight_qualifications: int = 20
    # The keywords an ATS would look for in a CV for this job, made once by the AI (screening_service.ats_keywords):
    # {"source": fingerprint of the job text they were made from, "keywords": [...]}. Made again when the job changes.
    ats_keywords: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
