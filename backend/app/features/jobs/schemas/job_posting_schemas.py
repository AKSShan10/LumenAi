"""Response body for the posts of a job."""
from datetime import datetime

from pydantic import BaseModel


class PostingOut(BaseModel):
    id: int
    job_id: int
    channel: str
    text: str
    apply_url: str
    status: str                      # posted | failed
    error: str = ""
    message_link: str = ""
    created_at: datetime
