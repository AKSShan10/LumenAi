"""Table `company_document`: one text of the company that the AI looks up before it writes a job (RAG).

Two kinds:
    job_description   a past job description -> the AI follows its structure, tone and wording
    policy            a company policy note   -> the AI follows its rules (for example an equal-opportunity statement)
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class CompanyDocument(SQLModel, table=True):
    __tablename__ = "company_document"
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(default="job_description", index=True)   # job_description | policy
    title: str
    text: str = Field(sa_column=Column(Text))
    source: str = "added"                             # added (by the interviewer) | approved job
    job_id: Optional[int] = Field(default=None, index=True)    # the approved job it came from, if any
    embedding: Optional[list] = Field(default=None, sa_column=Column(JSON))   # None = search by words only
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
