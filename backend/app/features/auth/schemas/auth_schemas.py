"""Request and response bodies for interviewer login."""
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    passcode: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    token: str
