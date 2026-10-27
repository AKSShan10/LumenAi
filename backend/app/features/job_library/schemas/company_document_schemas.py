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
    preview: str = ""              # the first words of the text, shown on the Knowledge base card
    created_at: datetime


class DocumentText(DocumentOut):
    """One document with its whole text (the "View" button of the Knowledge base)."""
    text: str


class DocumentHit(BaseModel):
    """One search result: which document the AI would be given, and how similar it is."""
    id: int
    kind: str
    title: str
    similarity: float
