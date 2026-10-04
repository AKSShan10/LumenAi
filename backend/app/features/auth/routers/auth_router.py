"""Interviewer login.

  POST /api/auth/login   passcode -> token (send it as  Authorization: Bearer <token>)
"""
from fastapi import APIRouter, HTTPException

from app.core.security import check_passcode, create_token
from app.features.auth.schemas.auth_schemas import LoginIn, LoginOut

router = APIRouter(prefix="/api/auth", tags=["Login"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn):
    if not check_passcode(body.passcode):
        raise HTTPException(401, "Wrong passcode")
    return LoginOut(token=create_token("interviewer"))
