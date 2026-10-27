"""Table `interview_quality`: the quality of one interview's process (F10). One row per interview.

    status           running | done | failed
    quality_score    the average of the five scores (0-100)
    scores           [{"key", "name", "score"}]: question relevance, competency coverage, answer signal,
                     speaking balance, consistency (None when it cannot be measured)
    talk             {"interviewer_sec", "candidate_sec", "interviewer_share", "longest_interviewer_sec", "balanced"}
    coverage         [{"requirement", "required", "state", "questions"}]  state: shown | no_signal | not_asked
    questions        [{"n", "question", "requirements", "relevance", "open", "reason", "better", "signal",
                       "signal_reason", "time"}]
    consistency      {"interviews": [...], "uneven": [...], "score"}  the same job's analysed interviews
    recommendations  [{"basis", "ref", "text", "time"}]  each based on one measured fact (checked by code)
It judges the process, never a person, and never changes a candidate's score or a decision.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class InterviewQuality(SQLModel, table=True):
    __tablename__ = "interview_quality"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True, unique=True)   # one result per interview (a new run replaces it)
    status: str = "running"                            # running | done | failed
    error: str = Field(default="", sa_column=Column(Text))
    quality_score: Optional[float] = None
    scores: list = Field(default_factory=list, sa_column=Column(JSON))
    talk: dict = Field(default_factory=dict, sa_column=Column(JSON))
    coverage: list = Field(default_factory=list, sa_column=Column(JSON))
    questions: list = Field(default_factory=list, sa_column=Column(JSON))
    consistency: dict = Field(default_factory=dict, sa_column=Column(JSON))
    summary: str = Field(default="", sa_column=Column(Text))
    recommendations: list = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
