"""Simple login with JWT.

- The interviewer logs in with a passcode and gets a token that lasts TOKEN_HOURS.
- The browser sends it with every request:  Authorization: Bearer <token>
- Logging out means the browser forgets the token; nothing is stored on the server.
"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from app.core import config


def _secret() -> str:
    if not config.SECRET_KEY:
        raise HTTPException(503, "Login is not configured: set SECRET_KEY in .env")
    return config.SECRET_KEY


def check_passcode(passcode: str) -> bool:
    return bool(config.INTERVIEWER_PASSCODE) and secrets.compare_digest(passcode, config.INTERVIEWER_PASSCODE)


def create_token(role: str = "interviewer") -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS)
    return jwt.encode({"role": role, "exp": expires}, _secret(), algorithm="HS256")


def is_valid_token(token: str) -> bool:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"]).get("role") == "interviewer"
    except (jwt.PyJWTError, HTTPException):
        return False
