"""Interviewer accounts and login: the account is in the database, the password is saved as a hash."""
from datetime import datetime, timedelta, timezone

import jwt
from sqlmodel import Session, select

from app.core import config, security
from app.core.database import engine
from app.features.auth.models import User
from app.features.auth.services.auth_service import check_password, hash_password

GOOD = {"email": "interviewer@example.com", "password": "test-passcode"}


def test_right_email_and_password_give_a_token(anonymous):
    response = anonymous.post("/api/auth/login", json=GOOD)
    assert response.status_code == 200
    assert (response.json()["email"], response.json()["full_name"]) == ("interviewer@example.com", "Test Interviewer")
    assert security.is_valid_token(response.json()["token"])
    # capital letters and spaces around the email do not matter
    assert anonymous.post("/api/auth/login", json={**GOOD, "email": " Interviewer@Example.com "}).status_code == 200


def test_wrong_email_or_password(anonymous):
    for body in ({**GOOD, "password": "wrong"}, {**GOOD, "email": "someone.else@example.com"}):
        response = anonymous.post("/api/auth/login", json=body)
        assert response.status_code == 401 and response.json()["detail"] == "Wrong email or password"
    assert anonymous.post("/api/auth/login", json={**GOOD, "password": ""}).status_code == 422


def test_the_password_is_saved_as_a_hash():
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == GOOD["email"])).one()
    assert "test-passcode" not in user.password_hash and user.password_hash.startswith("pbkdf2_sha256$")
    assert check_password("test-passcode", user.password_hash) and not check_password("wrong", user.password_hash)
    assert hash_password("same") != hash_password("same")                    # a new random salt every time
    assert check_password("anything", "not-a-hash") is False


def test_the_first_run_screen_works_only_once(anonymous):
    assert anonymous.get("/api/auth/status").json() == {"has_account": True}
    second = anonymous.post("/api/auth/setup", json={"full_name": "Someone Else", "email": "other@example.com",
                                                     "password": "another-password"})
    assert second.status_code == 409 and "already exists" in second.json()["detail"]
    assert anonymous.post("/api/auth/login", json={"email": "other@example.com", "password": "another-password"}).status_code == 401


def test_first_account_is_created_on_an_empty_database(tmp_path):
    """A fresh database: no account yet, the first-run screen creates it, and the person is logged in."""
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, create_engine
    from app.core.database import get_session
    from app.main import app
    fresh = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(fresh)

    def fresh_session():
        with Session(fresh) as session:
            yield session
    app.dependency_overrides[get_session] = fresh_session
    try:
        visitor = TestClient(app)
        assert visitor.get("/api/auth/status").json() == {"has_account": False}
        assert visitor.post("/api/auth/login", json=GOOD).status_code == 401
        bad = {"full_name": "Shan", "email": "not-an-email", "password": "long-enough"}
        assert visitor.post("/api/auth/setup", json=bad).status_code == 422
        assert visitor.post("/api/auth/setup", json={**bad, "email": "shan@example.com", "password": "short"}).status_code == 422
        created = visitor.post("/api/auth/setup", json={"full_name": "Shan", "email": "Shan@Example.com", "password": "long-enough"})
        assert created.status_code == 201 and created.json()["email"] == "shan@example.com"
        assert security.is_valid_token(created.json()["token"])
        assert visitor.get("/api/auth/status").json() == {"has_account": True}
    finally:
        app.dependency_overrides.clear()


def test_change_password(client, anonymous):
    assert anonymous.post("/api/auth/change-password", json={"current_password": "x", "new_password": "new-password-1"}).status_code == 401
    wrong = client.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "new-password-1"})
    assert wrong.status_code == 400 and "current password" in wrong.json()["detail"]
    assert client.post("/api/auth/change-password", json={"current_password": "test-passcode", "new_password": "short"}).status_code == 422

    assert client.post("/api/auth/change-password", json={"current_password": "test-passcode", "new_password": "new-password-1"}).status_code == 204
    assert anonymous.post("/api/auth/login", json=GOOD).status_code == 401                    # the old one is gone
    assert anonymous.post("/api/auth/login", json={**GOOD, "password": "new-password-1"}).status_code == 200
    # put it back, so the other tests can still log in
    assert client.post("/api/auth/change-password", json={"current_password": "new-password-1", "new_password": "test-passcode"}).status_code == 204


def test_missing_secret_key_is_reported(anonymous, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "")
    response = anonymous.post("/api/auth/login", json=GOOD)
    assert response.status_code == 503 and "SECRET_KEY" in response.json()["detail"]


def test_expired_token_is_not_valid():
    expired = jwt.encode({"role": "interviewer", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         config.SECRET_KEY, algorithm="HS256")
    assert security.is_valid_token(expired) is False


def test_token_signed_with_another_key_is_not_valid():
    forged = jwt.encode({"role": "interviewer", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "some-other-key-that-is-long-enough-123", algorithm="HS256")
    assert security.is_valid_token(forged) is False


# ---------- more accounts ----------

NEW = {"full_name": "Second Interviewer", "email": "Second@Example.com", "password": "second-password"}


def test_a_logged_in_interviewer_registers_and_removes_accounts(client, anonymous):
    created = client.post("/api/auth/users", json=NEW)
    assert created.status_code == 201 and created.json()["email"] == "second@example.com"
    assert "password" not in str(created.json())                                    # no password or hash is sent back
    assert client.post("/api/auth/users", json=NEW).status_code == 409             # the same email twice
    assert client.post("/api/auth/users", json={**NEW, "email": "bad"}).status_code == 422
    assert client.post("/api/auth/users", json={**NEW, "email": "x@example.com", "password": "short"}).status_code == 422

    # the new person logs in with their own password and can use the app
    token = anonymous.post("/api/auth/login", json={"email": "second@example.com", "password": "second-password"}).json()["token"]
    theirs = {"Authorization": f"Bearer {token}"}
    assert anonymous.get("/api/jobs", headers=theirs).status_code == 200
    users = anonymous.get("/api/auth/users", headers=theirs).json()
    assert [u["email"] for u in users] == ["interviewer@example.com", "second@example.com"]

    # nobody removes their own account, so one always stays; another one can be removed
    me, second = users
    assert client.delete(f"/api/auth/users/{me['id']}").status_code == 400
    assert client.delete(f"/api/auth/users/{second['id']}").status_code == 204
    assert client.delete(f"/api/auth/users/{second['id']}").status_code == 404
    assert anonymous.post("/api/auth/login", json={"email": "second@example.com", "password": "second-password"}).status_code == 401


def test_accounts_need_login(anonymous):
    assert anonymous.get("/api/auth/users").status_code == 401
    assert anonymous.post("/api/auth/users", json=NEW).status_code == 401
    assert anonymous.delete("/api/auth/users/1").status_code == 401
