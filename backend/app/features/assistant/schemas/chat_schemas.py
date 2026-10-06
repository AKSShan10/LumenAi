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
    kind: str                        # approve_job | post_telegram
    job_id: int
    job_title: str
    text: str = ""
    apply_url: str = ""
    status: str                      # pending | done | cancelled | failed
    result: str = ""


class ChatOut(BaseModel):
    messages: list[MessageOut]
    actions: list[ActionOut]         # the ones still waiting for an answer


class ConfirmIn(BaseModel):
    yes: bool
