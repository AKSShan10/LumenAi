"""Request and response bodies for the assistant."""
from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: int
    role: str                        # user | assistant
    content: str
    tools: list[str] = []            # which tools the assistant used for this answer
    attachment_name: str = ""
    created_at: datetime


class ActionOut(BaseModel):
    """Something the assistant prepared that waits for the interviewer's Yes or No."""
    id: int
    kind: str                        # approve_job | post_job
    job_id: int
    job_title: str
    text: str = ""
    apply_url: str = ""
    status: str                      # pending | done | cancelled | failed
    result: str = ""


class ChatSummary(BaseModel):
    """One line in the list of chats."""
    id: int
    title: str                       # the first thing the interviewer wrote
    started_at: datetime
    messages: int                    # how many lines it has


class ChatOut(BaseModel):
    chat_id: int                     # the chat these messages belong to
    is_current: bool                 # False = an earlier chat is shown: read it, or continue it
    messages: list[MessageOut]
    actions: list[ActionOut]         # the ones still waiting for an answer (current chat only)
    chats: list[ChatSummary]         # all chats, the current one first


class ConfirmIn(BaseModel):
    yes: bool
