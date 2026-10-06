"""Shared test settings. Offline: the fake AI is used, so no key is needed.

Database for tests:
  - TEST_DATABASE_URL set  -> that PostgreSQL database (its tables are dropped and recreated!)
                               e.g. postgresql+psycopg://recruit:recruit@localhost:5432/recruit_test
  - not set                -> a throw-away SQLite file, so tests also run without PostgreSQL
Never point TEST_DATABASE_URL at your real database.
"""
import os

TEST_DB = os.getenv("TEST_DATABASE_URL", "sqlite:///./test.db")
os.environ.update({
    "DATABASE_URL": TEST_DB,
    "LLM_PROVIDER": "fake",
    "TELEGRAM_PROVIDER": "fake",
    "INTERVIEWER_PASSCODE": "test-passcode",
    "SECRET_KEY": "test-secret-key-that-is-long-enough-123",
})
if os.path.exists("test.db"):
    os.remove("test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.core import all_models  # noqa: E402,F401  (registers every table)
from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402

if TEST_DB.startswith("postgresql"):
    SQLModel.metadata.drop_all(engine)   # start every test run with empty tables


@pytest.fixture(scope="session")
def client():
    """A logged-in interviewer."""
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"passcode": "test-passcode"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        c.token = token
        yield c


@pytest.fixture(scope="session")
def anonymous():
    """Someone who is not logged in (for example, a candidate)."""
    with TestClient(app) as c:
        yield c
