"""Response bodies of the CV claim verification (F8)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ClaimItem(BaseModel):
    claim: str                         # one checkable claim from the CV, e.g. "Five years of FastAPI work"
    cv_quote: str                      # the CV words it comes from (checked by code)
    status: str                        # supported | contradicted | unverified | not_discussed
    interview_quote: str = ""          # the candidate's own words (checked by code); "" when not discussed
    time: Optional[float] = None       # when that was said, seconds from the interview start
    note: str = ""                     # one neutral sentence: what was found
    follow_up: str = ""                # a question for the interviewer to ask ("" when supported)


class ClaimCheckOut(BaseModel):
    candidate_id: int
    session_id: Optional[int] = None
    status: str                        # not_started | running | done | failed
    error: str = ""
    claims: list[ClaimItem] = []
    updated_at: Optional[datetime] = None
