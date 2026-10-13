"""Request and response bodies for interviewer accounts and login."""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# Checks that the email looks like name@domain.tld and returns it trimmed; used by SetupIn
def _check_email(email: str) -> str:
    email = email.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Type a full email address, like you@company.com")
    return email


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class SetupIn(BaseModel):
    """A new interviewer account: the first one (first-run screen) or one more (Settings page)."""
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)

    _email = field_validator("email")(_check_email)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class LoginOut(BaseModel):
    token: str
    email: str                       # shown in the sidebar
    full_name: str = ""


class UserOut(BaseModel):
    """One account in the list on the Settings page. The password hash is never sent."""
    id: int
    email: str
    full_name: str
    created_at: datetime


class StatusOut(BaseModel):
    has_account: bool                # False = show the first-run screen instead of the login page
