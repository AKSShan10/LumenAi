"""Shapes of a job profile: what the assistant's save tool checks (JobCreate) and what the list shows (JobOut)."""
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
