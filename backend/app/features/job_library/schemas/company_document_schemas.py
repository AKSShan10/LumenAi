"""Response bodies for the company documents."""
from datetime import datetime

from pydantic import BaseModel


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
