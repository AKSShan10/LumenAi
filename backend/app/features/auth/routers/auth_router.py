"""Interviewer account and login.

  GET  /api/auth/status            is there an account yet? (no login needed)
  POST /api/auth/setup             first run only: create the interviewer account, and log in
  POST /api/auth/login             email + password -> token (send it as  Authorization: Bearer <token>)
  POST /api/auth/change-password   for the logged-in interviewer
  GET    /api/auth/users           the accounts (logged-in interviewers only)
  POST   /api/auth/users           register one more interviewer account
  DELETE /api/auth/users/{id}      remove an account (not your own)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import create_token, current_email, require_interviewer
from app.features.auth.models import User
from app.features.auth.schemas import ChangePasswordIn, LoginIn, LoginOut, SetupIn, StatusOut, UserOut
from app.features.auth.services.auth_service import (
    add_user, change_password, create_first_user, find_by_login, has_account, remove_user)

router = APIRouter(prefix="/api/auth", tags=["Login"])


# Builds the login answer: a new interviewer token (create_token) plus the user's email and name
def _logged_in(user: User) -> LoginOut:
    # → signs the JWT that later passes require_interviewer (core/security.py)
    return LoginOut(token=create_token("interviewer", user.email), email=user.email, full_name=user.full_name)


# GET /api/auth/status: tells the page if any account exists yet, so it can show the first-run screen
@router.get("/status", response_model=StatusOut)
def status(session: Session = Depends(get_session)):
    return StatusOut(has_account=has_account(session))


# POST /api/auth/setup: creates the first interviewer account and logs in (create_first_user)
@router.post("/setup", response_model=LoginOut, status_code=201)
def setup(body: SetupIn, session: Session = Depends(get_session)):
    return _logged_in(create_first_user(session, body.full_name, body.email, body.password))


# POST /api/auth/login: checks email and password (find_by_login) and returns a token, or 401
@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, session: Session = Depends(get_session)):
    user = find_by_login(session, body.email, body.password)
    if not user:
        raise HTTPException(401, "Wrong email or password")       # never says which of the two was wrong
    return _logged_in(user)


# POST /api/auth/change-password: changes the logged-in user's password (change_password)
@router.post("/change-password", status_code=204)
def new_password(body: ChangePasswordIn, email: str = Depends(current_email), session: Session = Depends(get_session)):
    change_password(session, email, body.current_password, body.new_password)


# ---------- more accounts: only someone who is already logged in can register or remove one ----------

# GET /api/auth/users: returns all interviewer accounts (login needed)
@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_interviewer)])
def list_users(session: Session = Depends(get_session)):
    return session.exec(select(User).order_by(User.id)).all()


# POST /api/auth/users: a logged-in interviewer adds one more account (add_user)
@router.post("/users", response_model=UserOut, status_code=201, dependencies=[Depends(require_interviewer)])
def register_user(body: SetupIn, session: Session = Depends(get_session)):
    return add_user(session, body.full_name, body.email, body.password)


# DELETE /api/auth/users/{user_id}: removes an account, but never your own (remove_user)
@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, email: str = Depends(current_email), session: Session = Depends(get_session)):
    remove_user(session, user_id, email)
