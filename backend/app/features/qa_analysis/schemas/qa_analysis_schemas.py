"""Response bodies of the Q&A analysis."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class QaItemOut(BaseModel):
    position: int
    question: str
    answer: str
    job_related: bool                # False = small talk (kept, not graded)
    split_from_multi_part: bool
    relevance: Optional[int] = None  # 0 to 100
    accuracy: Optional[int] = None
    completeness: Optional[int] = None
    articulation: Optional[int] = None
    score: Optional[float] = None    # the average of the four
    reasons: dict = {}               # one sentence per grade
    evidence_quote: str = ""
    evidence_time: Optional[float] = None   # seconds from the interview start
    requirements: list[str] = []
    references: list[str] = []       # company documents used for accuracy
    follow_up: str = ""              # a suggested follow-up question for what the answer missed


class QaAnalysisOut(BaseModel):
    session_id: int
    status: str                      # not_started | running | done | failed
    error: str = ""
    interview_score: Optional[float] = None
    covered: list[str] = []
    uncovered: list[str] = []
    created_at: Optional[datetime] = None
    items: list[QaItemOut] = []
