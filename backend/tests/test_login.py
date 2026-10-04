"""Tests for interviewer login: passcode in, token out."""
from datetime import datetime, timedelta, timezone

import jwt

from app.core import config, security


def test_right_passcode_gives_a_token(anonymous):
    response = anonymous.post("/api/auth/login", json={"passcode": "test-passcode"})
    assert response.status_code == 200
    assert security.is_valid_token(response.json()["token"])


def test_wrong_passcode(anonymous):
    response = anonymous.post("/api/auth/login", json={"passcode": "wrong"})
    assert response.status_code == 401 and response.json()["detail"] == "Wrong passcode"


def test_empty_passcode_is_rejected(anonymous):
    assert anonymous.post("/api/auth/login", json={"passcode": ""}).status_code == 422


def test_no_passcode_configured_means_nobody_gets_in(anonymous, monkeypatch):
    monkeypatch.setattr(config, "INTERVIEWER_PASSCODE", "")
    assert anonymous.post("/api/auth/login", json={"passcode": ""}).status_code == 422
    assert security.check_passcode("") is False


def test_missing_secret_key_is_reported(anonymous, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "")
    response = anonymous.post("/api/auth/login", json={"passcode": "test-passcode"})
    assert response.status_code == 503 and "SECRET_KEY" in response.json()["detail"]


def test_expired_token_is_not_valid():
    expired = jwt.encode({"role": "interviewer", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         config.SECRET_KEY, algorithm="HS256")
    assert security.is_valid_token(expired) is False


def test_token_signed_with_another_key_is_not_valid():
    forged = jwt.encode({"role": "interviewer", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "some-other-key-that-is-long-enough-123", algorithm="HS256")
    assert security.is_valid_token(forged) is False
