"""Interviewer accounts: saved in the database, never in .env.

    hash_password()       turns a password into a hash that cannot be turned back
    check_password()      does a typed password give the same hash?
    has_account()         is there an account yet? (the first-run screen is shown while there is none)
    create_first_user()   the first-run screen: creates the first interviewer account
    add_user()            a logged-in interviewer registers one more account
    remove_user()         removes an account (never your own)
    find_by_login()       the user for an email and password, or None
    change_password()     for the logged-in user

Why a hash: if someone reads the table, they see scrambled text, not the password. Every password gets its
own random "salt", so two people with the same password have different hashes. The scrambling is repeated
many times on purpose, which makes guessing slow. This is PBKDF2 from Python's own library.
"""
import hashlib
import secrets

from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.auth.models import User

ROUNDS = 200_000                 # how often the scrambling is repeated


def hash_password(password: str) -> str:
    """Returns "pbkdf2_sha256$<rounds>$<salt>$<hash>": everything needed to check a password later."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()
    return f"pbkdf2_sha256${ROUNDS}${salt}${digest}"


# Hashes the typed password with the saved salt and rounds and compares it to the saved hash
def check_password(password: str, saved: str) -> bool:
    try:
        _, rounds, salt, digest = saved.split("$")
        again = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    except ValueError:
        return False
    return secrets.compare_digest(again, digest)


# Returns True when at least one user exists in the database
def has_account(session: Session) -> bool:
    return session.exec(select(User.id)).first() is not None


# Creates the very first account (add_user); refuses with 409 if an account already exists
def create_first_user(session: Session, full_name: str, email: str, password: str) -> User:
    if has_account(session):
        raise HTTPException(409, "An account already exists. Log in with it.")
    return add_user(session, full_name, email, password)


def add_user(session: Session, full_name: str, email: str, password: str) -> User:
    """One more interviewer account. Only someone who is logged in may call this (see the router)."""
    email = email.strip().lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(409, "An account with this email address already exists")
    user = User(email=email, full_name=full_name.strip(), password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# Deletes a user by id; refuses if it is not found or if it is the logged-in user's own account
def remove_user(session: Session, user_id: int, my_email: str) -> None:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Account not found")
    if user.email == my_email:
        raise HTTPException(400, "You cannot remove your own account")      # so there is always one account left
    session.delete(user)
    session.commit()


# Returns the user for this email and password, or None (wrong email takes the same time)
def find_by_login(session: Session, email: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.email == email.strip().lower())).first()
    if not user:
        hash_password(password)                       # spend the same time, so a wrong email is not answered faster
        return None
    return user if check_password(password, user.password_hash) else None


# Checks the current password (find_by_login), then saves a hash of the new one
def change_password(session: Session, email: str, current_password: str, new_password: str) -> None:
    user = find_by_login(session, email, current_password)
    if not user:
        raise HTTPException(400, "The current password is not right")
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
