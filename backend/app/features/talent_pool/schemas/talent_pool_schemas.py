"""Request and response bodies of the talent pool."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PoolEntryIn(BaseModel):
    """Add a candidate to the pool, or change the status and note."""
    status: Literal["strong", "other_role"] = "strong"
    note: str = Field(default="", max_length=500)
    add_back: bool = False           # True = add again someone who unsubscribed (the interviewer confirmed it)


class PoolEntryOut(BaseModel):
    """Is this candidate in the pool? (the card on the assessment report)"""
    in_pool: bool
    status: str = ""
    note: str = ""
    added_at: Optional[datetime] = None
    keep_until: Optional[datetime] = None
    unsubscribed: bool = False


class InviteSent(BaseModel):
    job_title: str
    sent_at: datetime
    applied: bool                    # the same email applied to that job afterwards


class PoolRow(BaseModel):
    """One person on the Talent Pool page."""
    candidate_id: int
    name: str
    email: str
    from_job: str                    # the job they applied to
    status: str
    note: str
    added_at: datetime
    keep_until: datetime
    state: str                       # active | unsubscribed | expired
    invites: list[InviteSent] = []


class MatchRow(BaseModel):
    """A pool candidate who may fit a new job. The match is worked out by code, never by the AI."""
    pool_id: int
    candidate_id: int
    name: str
    from_job: str
    status: str
    overall_score: Optional[float] = None    # their earlier assessment, if any
    decision: str = ""
    match: int                               # % of the new job's requirements found in their CV
    matched: list[str] = []
    missing: list[str] = []
    invited_at: Optional[datetime] = None    # already invited to this job


class MatchesOut(BaseModel):
    min_match: int                           # the minimum match % that was used (POOL_MIN_MATCH if none was given)
    rows: list[MatchRow] = []


class DraftIn(BaseModel):
    pool_ids: list[int] = Field(min_length=1, max_length=20)
    instruction: str = Field(default="", max_length=300)    # "Write again" with a wish, e.g. "shorter"
    previous_subject: str = Field(default="", max_length=200)   # "Write again" for one person: the draft on the page,
    previous_body: str = Field(default="", max_length=4000)     # so the AI improves it instead of starting again


class InviteDraft(BaseModel):
    """One invitation the AI drafted; the interviewer may change it before sending."""
    pool_id: int
    name: str
    email: str
    subject: str = Field(max_length=200)
    body: str = Field(max_length=4000)
    footer: str = ""                 # the links code adds below the text (shown as a preview; never taken from the page)


class SendIn(BaseModel):
    invites: list[InviteDraft] = Field(min_length=1, max_length=20)


class InviteResult(BaseModel):
    pool_id: int
    name: str
    ok: bool
    error: str = ""


class UnsubscribeOut(BaseModel):
    """The public unsubscribe page: only the first name, nothing else."""
    first_name: str
    unsubscribed: bool
