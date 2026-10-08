"""Request and response bodies for screening."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ScreenIn(BaseModel):
    again: bool = False              # true: screen every CV of the job again (the interviewer's decisions are kept)


class ScreenOut(BaseModel):
    ok: bool
    message: str
    screened: int = 0                # candidates screened in this click
    left: int = 0                    # candidates that still wait


class ScreeningRowOut(BaseModel):
    """One candidate of the job with the screening result (None = not screened yet)."""
    candidate_id: int
    full_name: str
    result: Optional[str] = None     # the system result: passed | excluded | needs_review | None (not screened)
    reason: str = ""
    final: Optional[str] = None      # what counts: included | excluded | needs_review (the person's decision wins)
    waiting: bool = False            # waits for (another) screening
    decision: str = ""               # the interviewer's decision: included | excluded | "" (none)
    decision_note: str = ""
    decided_by: str = ""
    decided_at: Optional[datetime] = None
    skills: list[str] = []
    total_years: float = 0
    education: list[str] = []
    matches: list[dict] = []
    must_met: int = 0
    must_total: int = 0
    nice_met: int = 0
    nice_total: int = 0
    screened_at: Optional[datetime] = None
    sections: dict = {}              # F4: {"skills": {score, reason, quote, proof}, "experience": ..., "qualifications": ...}
    weighted_score: Optional[float] = None
    ats: dict = {}                   # ATS match: {score, matched, missing, total}
    ats_score: Optional[float] = None


class ProgressOut(BaseModel):
    """The latest screening run of a job, for the progress bar: "Screening 3 of 7 CVs"."""
    running: bool
    total: int = 0
    done: int = 0
    included: int = 0
    excluded: int = 0
    needs_review: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    message: str = ""


class DecisionIn(BaseModel):
    """The interviewer's decision. decision null = undo: the system result counts again. The note is optional."""
    decision: Literal["included", "excluded"] | None
    note: str = Field(default="", max_length=500)


class WeightsIn(BaseModel):
    """How much each section counts in the weighted score. Whole numbers that add up to 100."""
    skills: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    qualifications: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def add_up_to_100(self):
        if self.skills + self.experience + self.qualifications != 100:
            raise ValueError("The three weights must add up to 100")
        return self


class WeightsOut(BaseModel):
    skills: int
    experience: int
    qualifications: int
    updated: int = 0                 # how many screened candidates got a new weighted score
