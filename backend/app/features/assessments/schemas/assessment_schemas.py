"""Request and response bodies of the assessment."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    text: str                        # one sentence, e.g. "Built REST APIs with FastAPI for three years."
    quote: str                       # words copied from the CV or the candidate's answers (checked by code)
    source: str                      # CV | Interview


class AreaItem(BaseModel):
    area: str                        # what to explore further, e.g. "PostgreSQL indexing"
    why: str


class AssessmentOut(BaseModel):
    candidate_id: int
    candidate_name: str = ""
    job_id: int
    job_title: str = ""
    session_id: Optional[int] = None
    status: str                      # not_started | running | done | failed
    error: str = ""
    cv_score: Optional[float] = None
    interview_score: Optional[float] = None
    cv_weight: int = 40
    overall_score: Optional[float] = None
    summary: str = ""
    strengths: list[EvidenceItem] = []
    weaknesses: list[EvidenceItem] = []
    evidence_gaps: list[str] = []
    recommended_areas: list[AreaItem] = []
    repair_rounds: int = 0
    decision: str = "pending"        # pending | hire | hold | reject
    decision_note: str = ""
    decided_by: str = ""
    decided_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DecisionIn(BaseModel):
    """The interviewer's decision. "pending" takes a decision back."""
    decision: Literal["pending", "hire", "hold", "reject"]
    note: str = Field(default="", max_length=1000)


class WeightIn(BaseModel):
    """The CV part of the overall score in %, set on the Reports page; the interview is the rest (100 - cv_weight)."""
    cv_weight: int = Field(ge=0, le=100)


class ComparisonRow(BaseModel):
    """One candidate of the job in the comparison table."""
    candidate_id: int
    candidate_name: str
    interview_ended: bool            # an interview of this candidate has ended
    analysis_done: bool              # its answers have been analysed (needed for the assessment)
    status: str                      # the assessment: not_started | running | done | failed
    cv_score: Optional[float] = None
    interview_score: Optional[float] = None
    overall_score: Optional[float] = None
    cv_weight: int = 40              # the CV part of the overall score, in %
    decision: str = "pending"
