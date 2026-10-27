"""Table `claim_check`: the CV claims of one candidate compared with the interview (F8). One row per candidate.

    status   running | done | failed
    claims   [{"claim", "cv_quote", "status", "interview_quote", "time", "note", "follow_up"}]
             status: supported | contradicted | unverified | not_discussed (code checked every quote)
These are prompts for the interviewer's follow-up questions: never an accusation, never a score or a decision.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ClaimCheck(SQLModel, table=True):
    __tablename__ = "claim_check"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, unique=True)  # one check per candidate (a new run replaces it)
    session_id: Optional[int] = None                  # the interview whose transcript was used
    status: str = "running"                           # running | done | failed
    error: str = Field(default="", sa_column=Column(Text))
    claims: list = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
