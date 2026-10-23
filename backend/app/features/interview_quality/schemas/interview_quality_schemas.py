"""Response body of the interview quality assessment (F10). The lists are described in the model's docstring."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InterviewQualityOut(BaseModel):
    session_id: int
    status: str                        # not_started | running | done | failed
    error: str = ""
    quality_score: Optional[float] = None
    scores: list[dict] = []            # the five scores behind the quality score
    talk: dict = {}                    # speaking time per speaker
    coverage: list[dict] = []          # each job requirement: shown | no_signal | not_asked
    questions: list[dict] = []         # each interviewer question: relevance, open, signal, a better wording
    consistency: dict = {}             # the same job's interviews side by side
    summary: str = ""
    recommendations: list[dict] = []   # improvements, each based on one measured fact
    updated_at: Optional[datetime] = None
