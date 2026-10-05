"""Request and response bodies for the company documents."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["job_description", "policy"]


class DocumentIn(BaseModel):
    kind: Kind = "job_description"
    title: str = Field(min_length=2, max_length=120)
    text: str = Field(min_length=1, max_length=20000)


class DocumentOut(BaseModel):
    id: int
    kind: str
    title: str
    source: str
    job_id: int | None = None
    words: int
    created_at: datetime


class DocumentHit(BaseModel):
    """One search result: which document the AI would be given, and how similar it is."""
    id: int
    kind: str
    title: str
    similarity: float
