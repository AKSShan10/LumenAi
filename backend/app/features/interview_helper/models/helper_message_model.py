"""Table `helper_message`: what the interviewer asked the AI helper, and what it answered.

    kind "questions"   one list of suggested questions (role helper); text = the topic the interviewer typed
    kind "chat"        one chat message, from the interviewer or from the helper
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class HelperMessage(SQLModel, table=True):
    __tablename__ = "helper_message"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)               # the interview (interview_session)
    role: str                                         # interviewer | helper
    kind: str                                         # chat | questions
    text: str = Field(default="", sa_column=Column(Text))
    # kind "questions": [{"question", "requirement", "why", "model_answer"}]
    questions: list = Field(default_factory=list, sa_column=Column(JSON))
    # RAG: the titles of the company notes behind this answer ([] = no company document was similar enough)
    sources: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
