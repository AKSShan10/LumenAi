"""Table `call_message`: the chat inside a video call (text and links), between the interviewer and the candidate.

(The Assistant chat already uses the table name chat_message, so the call chat has its own name.)
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class CallMessage(SQLModel, table=True):
    __tablename__ = "call_message"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)               # the interview (interview_session)
    sender: str                                       # interviewer | candidate (the role, e.g. for a transcript)
    sender_name: str = ""                             # the name shown in the chat, saved when the message is sent
    text: str = Field(sa_column=Column(Text))
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
