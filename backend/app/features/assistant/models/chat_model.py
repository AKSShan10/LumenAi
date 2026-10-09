"""Tables of the assistant chat.

    chat_conversation   one chat. "New chat" starts a new one; the earlier ones are kept and can be continued

    chat_message        one line of the conversation (the interviewer or the assistant)
    assistant_action    something the assistant wants to do that needs a person's Yes first
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ChatConversation(SQLModel, table=True):
    """The chat that was opened last is the current one. The others are earlier chats: they can be read,
    and "Continue this chat" makes one of them the current chat again."""
    __tablename__ = "chat_conversation"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))   # set by "New chat" and "Continue this chat"
    # LangGraph's memory of this chat: the agent's thread in the checkpointer, and the last chat line it was given
    agent_thread: str = Field(default="")             # "" = no thread yet (a new one is made with the next message)
    agent_seen_id: int = Field(default=0)             # chat_message.id of the last line the agent already has


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(default=0, index=True)                  # which chat this line belongs to
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
    kind: str                                         # approve_job | post_job
    job_id: int
    job_title: str = ""
    text: str = Field(default="", sa_column=Column(Text))         # the post (post_job only)
    apply_url: str = ""                               # the application form link (post_job only)
    status: str = "pending"                           # pending | done | cancelled | failed
    result: str = Field(default="", sa_column=Column(Text))       # what happened, in one sentence
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
