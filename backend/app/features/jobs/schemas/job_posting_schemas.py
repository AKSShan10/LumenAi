"""Request and response bodies for posting a job to Telegram."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _check_link(url: str) -> str:
    url = url.strip()
    if not url.startswith("https://") or " " in url or len(url) < 12:
        raise ValueError("Paste the full link to the application form (it starts with https://)")
    return url


class PostTextOut(BaseModel):
    """The post made by code from the approved job: the same words the interviewer approved."""
    text: str


class PostDraftIn(BaseModel):
    # "Generate again": what the interviewer wants changed, and the post they did not like
    change_request: str = Field(default="", max_length=500)
    previous: str = Field(default="", max_length=3500)


class PostDraftOut(BaseModel):
    """The post the AI wrote. Not saved and not posted: it fills the box for the interviewer to check."""
    from_ai: bool
    message: str = ""                # why it failed, or what the interviewer should still check
    text: str = ""


class PostIn(BaseModel):
    text: str = Field(min_length=20, max_length=3500)
    apply_url: str = Field(max_length=500)

    _link = field_validator("apply_url")(_check_link)


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
