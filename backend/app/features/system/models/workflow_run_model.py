"""Table `workflow_run`: one run of the parent recruitment graph (the "Persist state" step).

Every time a person starts AI work, the parent graph writes one row here: which stage ran, for which
CV / interview / candidate, how it ended and how long it took.
It is a simple log for the interviewer and the developer; the results themselves are saved by each subgraph.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_run"
    id: Optional[int] = Field(default=None, primary_key=True)
    stage: str = Field(index=True)                   # pre_interview | interview_analysis | post_interview
    subject_id: int                                  # candidate id (pre / post) or interview session id
    outcome: str                                     # screened | excluded | needs_review | done | failed
    error: str = Field(default="", sa_column=Column(Text))
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    seconds: float = 0.0                             # how long the run took
