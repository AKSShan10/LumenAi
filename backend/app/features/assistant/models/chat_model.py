"""Tables of the assistant chat.

    chat_message        one line of the conversation (the interviewer or the assistant)
    assistant_action    something the assistant wants to do that needs a person's Yes first
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str                                         # user | assistant
    content: str = Field(default="", sa_column=Column(Text))
    tools: list = Field(default_factory=list, sa_column=Column(JSON))    # names of the tools the assistant used
    attachment_name: str = ""                         # a file sent with the message
    attachment_text: str = Field(default="", sa_column=Column(Text))     # the text read out of that file
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssistantAction(SQLModel, table=True):
    """The assistant may prepare these, but only a person can let them happen."""
    __tablename__ = "assistant_action"
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str                                         # approve_job | post_telegram
    job_id: int
    job_title: str = ""
    text: str = Field(default="", sa_column=Column(Text))         # the Telegram post (post_telegram only)
    apply_url: str = ""                               # the application form link (post_telegram only)
    status: str = "pending"                           # pending | done | cancelled | failed
    result: str = Field(default="", sa_column=Column(Text))       # what happened, in one sentence
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
