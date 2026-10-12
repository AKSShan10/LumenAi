"""Table `shortlist_entry`: the included candidates the interviewer chose for the next step (the interview invitation).

One row per candidate. Only an included candidate can be on the shortlist; a candidate who is excluded later
(by a person, or by screening again) is taken off it by the screening workflow (see shortlist_service.py).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ShortlistEntry(SQLModel, table=True):
    __tablename__ = "shortlist_entry"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    candidate_id: int = Field(index=True, unique=True)          # a candidate is on the shortlist at most once
    rule: str = ""                                    # how they were chosen: "Top 5", "Final score at least 70", "Added by hand"
    added_by: str = ""                                # the email of the interviewer who added them
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
