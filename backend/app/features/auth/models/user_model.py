"""Table `app_user`: a person who may log in as interviewer."""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """The password itself is never saved, only its hash (see auth_service.hash_password)."""
    __tablename__ = "app_user"                        # not "user": that word is reserved in PostgreSQL
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)       # saved in small letters
    full_name: str = ""
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
