"""Tests for the backend skeleton: the API starts, answers, and reaches the database."""
from sqlalchemy import text
from sqlmodel import Session

from app.core.database import engine, get_session


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["app_name"] == "LumenAI"


def test_api_docs_page(client):
    assert client.get("/docs").status_code == 200


def test_unknown_address(client):
    assert client.get("/api/does-not-exist").status_code == 404


def test_database_answers():
    with Session(engine) as session:
        assert session.exec(text("SELECT 1")).one()[0] == 1


def test_one_session_per_request():
    sessions = get_session()
    assert isinstance(next(sessions), Session)
    sessions.close()
