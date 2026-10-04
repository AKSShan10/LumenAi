"""Tests for role-based access: only a logged-in interviewer reaches the recruiting endpoints."""
import pytest

from app.core import security

INTERVIEWER_ONLY = ["/api/llm-check", "/api/workflow-runs"]


@pytest.mark.parametrize("path", INTERVIEWER_ONLY)
def test_not_logged_in_is_rejected(anonymous, path):
    response = anonymous.get(path)
    assert response.status_code == 401 and response.json()["detail"] == "Please log in"


@pytest.mark.parametrize("path", INTERVIEWER_ONLY)
def test_interviewer_is_allowed(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", INTERVIEWER_ONLY)
def test_candidate_token_is_rejected(anonymous, path):
    """Even a correctly signed token is refused when its role is not interviewer."""
    token = security.create_token("candidate")
    assert anonymous.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("header", ["Bearer not-a-real-token", "Basic abc", "Bearer "])
def test_bad_token_is_rejected(anonymous, header):
    assert anonymous.get("/api/llm-check", headers={"Authorization": header}).status_code == 401


def test_health_and_login_are_public(anonymous):
    assert anonymous.get("/api/health").status_code == 200
    assert anonymous.post("/api/auth/login", json={"passcode": "test-passcode"}).status_code == 200
