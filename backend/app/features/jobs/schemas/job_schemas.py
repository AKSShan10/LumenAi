"""Request and response bodies for job profiles."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=5000)
    required_skills: list[str] = Field(min_length=1, max_length=30)
    preferred_skills: list[str] = Field(default_factory=list, max_length=30)
    min_years: int = Field(default=0, ge=0, le=50)
    qualifications: str = Field(default="", max_length=300)
    prompt: str = Field(default="", max_length=2000)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def clean_skills(cls, skills: list[str]) -> list[str]:
        cleaned = [s.strip() for s in skills if s.strip()]
        return list(dict.fromkeys(cleaned))  # remove duplicates, keep order


class JobOut(JobCreate):
    id: int
    status: str = "draft"            # draft | approved
    approved_at: datetime | None = None


class PromptIn(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    # "Generate again": what the interviewer wants changed, and the description they did not like
    change_request: str = Field(default="", max_length=500)
    previous: str = Field(default="", max_length=5000)


class JobDraftOut(BaseModel):
    """What the AI made from the prompt. Not saved: it fills the job form for the interviewer to check."""
    from_ai: bool
    message: str = ""                # why it failed, or what the interviewer should still check
    title: str = ""
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    min_years: int = 0
    qualifications: str = ""
    description: str = ""
    examples: list[str] = []         # titles of the past job descriptions the AI followed (RAG)
    policies: list[str] = []         # titles of the company policy notes the AI followed (RAG)
    revisions: int = 0               # how often the check sent the draft back to the AI


class ApproveIn(BaseModel):
    add_to_library: bool = True      # keep the approved description as an example for future jobs
