"""Request and response bodies of the assessment."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    text: str                        # one sentence, e.g. "Built REST APIs with FastAPI for three years."
    quote: str                       # words copied from the CV or the candidate's answers (checked by code)
    source: str                      # CV | Interview
    time: Optional[float] = None     # Interview: when it was said, seconds from the interview start (link to transcript)


class AreaItem(BaseModel):
    area: str                        # what to explore further, e.g. "PostgreSQL indexing"
    why: str
    requirement: str = ""            # the job requirement it is about (checked: one of the job's own)
    quote: str = ""                  # proof from the CV or the answers (checked by code), or ""
    source: str = ""                 # CV | Interview | "" (no quote)
    time: Optional[float] = None     # Interview: when the quote was said


class PartScore(BaseModel):
    """One part behind a total score, e.g. CV "Skills" 80 or interview "Accuracy" 62.5."""
    name: str
    score: Optional[float] = None


class RequirementRow(BaseModel):
    """One job requirement: what the CV screening found and whether the interview showed it."""
    requirement: str
    kind: str = ""                   # must | nice
    cv: str = "unchecked"            # met | partial | unmet | unchecked (from the CV screening)
    cv_how: str = ""                 # the screening's one-sentence reason
    interview: Optional[bool] = None # True = shown in an answer, False = not shown, None = not a skill asked about


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
    # The parts behind the totals (read from the CV screening and the Q&A analysis when the report is opened)
    cv_parts: list[PartScore] = []           # skills, experience, qualifications
    interview_parts: list[PartScore] = []    # relevance, accuracy, completeness, articulation (averages)
    requirements: list[RequirementRow] = []  # every requirement: CV result and interview result
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
    evidence_gaps: list[str] = []    # requirements with no proof (from the report)
    top_strength: str = ""           # the first proven strength (from the report)
    decision: str = "pending"
