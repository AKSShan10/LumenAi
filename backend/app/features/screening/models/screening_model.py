"""Table `screening_result`: the screening of one candidate's CV against the job's requirements."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ScreeningResult(SQLModel, table=True):
    """One row per candidate. Screening the candidate again replaces it."""
    __tablename__ = "screening_result"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, unique=True)
    job_id: int = Field(index=True)
    # passed: every must-have is met | excluded: a must-have is missing | needs_review: a person must look
    result: str = "needs_review"
    reason: str = ""                                  # one sentence for the interviewer
    # What the AI read from the CV: skills, total_years, education, experience, language
    parsed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # One entry per requirement: {"requirement", "kind" (must | nice), "met" (true/false), "how"}
    matches: list = Field(default_factory=list, sa_column=Column(JSON))
    missing: list = Field(default_factory=list, sa_column=Column(JSON))   # the must-haves that are not met
    # F4 scores. Per section: {"score": 0-100, "reason": "...", "quote": "words copied from the CV", "proof": true/false}
    # for "skills", "experience" and "qualifications". Empty for a CV that needs review.
    sections: dict = Field(default_factory=dict, sa_column=Column(JSON))
    weighted_score: Optional[float] = None            # the sections combined with the job's weights (Python, 0-100)
    # ATS match: {"score": 0-100, "matched": [...], "missing": [...], "total": n} - the job's ATS keywords in the CV
    ats: dict = Field(default_factory=dict, sa_column=Column(JSON))
    ats_score: Optional[float] = None
    # The person's decision (human control). "" = none: the system result counts.
    decision: str = ""                                # included | excluded | ""
    decision_note: str = ""                           # optional reason the interviewer typed
    decided_by: str = ""                              # the email of the interviewer who decided
    decided_at: Optional[datetime] = None
    stale: bool = False                               # "Screen all again" was clicked: screen this CV again
    thread_id: str = ""                               # the LangGraph run that waits for the person (hr_review)
    # The text this screening used. For a scanned PDF it is what the AI read (OCR), so it is kept here.
    cv_text: str = Field(default="", sa_column=Column(Text))
    text_source: str = ""                             # file (read by code) | ai_read (the AI read the PDF) | ""
    read_problem: str = ""                            # why the text could not be used ("" = fine)
    model: str = ""                                   # the AI model that read the CV
    screened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
