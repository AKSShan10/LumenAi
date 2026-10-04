"""Simple login with JWT.

- The interviewer logs in with a passcode and gets a token that lasts TOKEN_HOURS.
- Every interviewer endpoint needs:  Authorization: Bearer <token>
- Logging out means the browser forgets the token; nothing is stored on the server.
- Candidates never get this token, so they cannot see jobs, CVs, scores or rankings.
  They only use the private link from their invitation.
"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import config

bearer = HTTPBearer(auto_error=False)


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


def require_interviewer(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    """FastAPI dependency: stops the request unless a valid interviewer token is sent.

    Protect a whole router with it:
        router = APIRouter(prefix="/api/jobs", dependencies=[Depends(require_interviewer)])
    """
    if not creds or not is_valid_token(creds.credentials):
        raise HTTPException(401, "Please log in")
