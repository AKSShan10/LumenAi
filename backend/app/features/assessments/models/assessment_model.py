"""Table `assessment`: the final report of one candidate (F6), made from the CV screening and the interview analysis.

    status running | done | failed
    strengths, weaknesses   [{"text", "quote", "source": "CV" | "Interview"}]; every quote is checked by code
    evidence_gaps           job requirements with no proof in the CV or the interview (code, not AI)
    recommended_areas       [{"area", "why"}]: what to explore in a next interview or reference check
    decision                pending | hire | hold | reject - recorded by a person, never by the AI
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class Assessment(SQLModel, table=True):
    __tablename__ = "assessment"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, unique=True)  # one assessment per candidate
    job_id: int = Field(index=True)
    session_id: Optional[int] = None                  # the interview whose analysis was used
    status: str = "running"                           # running | done | failed
    error: str = Field(default="", sa_column=Column(Text))
    cv_score: Optional[float] = None                  # from the CV screening (0-100)
    interview_score: Optional[float] = None           # from the Q&A analysis (0-100)
    cv_weight: int = 40                               # the CV part of the overall score, in % (ASSESSMENT_CV_WEIGHT)
    overall_score: Optional[float] = None             # CV x weight % + interview x (100 - weight) %
    summary: str = Field(default="", sa_column=Column(Text))
    strengths: list = Field(default_factory=list, sa_column=Column(JSON))
    weaknesses: list = Field(default_factory=list, sa_column=Column(JSON))
    evidence_gaps: list = Field(default_factory=list, sa_column=Column(JSON))
    recommended_areas: list = Field(default_factory=list, sa_column=Column(JSON))
    repair_rounds: int = 0                            # how often items without proof went back to the AI (max 2)
    decision: str = "pending"                         # pending | hire | hold | reject (a person decides)
    decision_note: str = Field(default="", sa_column=Column(Text))
    decided_by: str = ""                              # the email of the interviewer who decided
    decided_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
