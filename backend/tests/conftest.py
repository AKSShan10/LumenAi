"""Shared test settings. Offline: the fake AI is used, so no key is needed.

Database for tests:
  - TEST_DATABASE_URL set  -> that PostgreSQL database (its tables are dropped and recreated!)
                               e.g. postgresql+psycopg://recruit:recruit@localhost:5432/recruit_test
  - not set                -> a throw-away SQLite file, so tests also run without PostgreSQL
Never point TEST_DATABASE_URL at your real database.
"""
import os
import tempfile

TEST_DB = os.getenv("TEST_DATABASE_URL", "sqlite:///./test.db")
os.environ.update({
    "DATABASE_URL": TEST_DB,
    "LLM_PROVIDER": "fake",
    "BLOGGER_PROVIDER": "fake",
    "DRIVE_PROVIDER": "fake",
    "SCREENING_MODE": "manual",           # nothing screens by itself in the background during tests
    "STORAGE_DIR": tempfile.mkdtemp(prefix="lumenai-test-cvs-"),      # CV files of the tests; never the real folder
    "LOG_FILE": "",                       # tests write no log file
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


LOGIN = {"email": "interviewer@example.com", "password": "test-passcode"}      # the made-up account of the tests


@pytest.fixture(scope="session")
def client():
    """A logged-in interviewer."""
    with TestClient(app) as c:
        # the first run creates the interviewer account; after that it is a normal login
        c.post("/api/auth/setup", json={"full_name": "Test Interviewer", **LOGIN})
        token = c.post("/api/auth/login", json=LOGIN).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        c.token = token
        yield c


@pytest.fixture(scope="session")
def anonymous(client):
    """Someone who is not logged in (for example, a candidate). The interviewer account already exists."""
    with TestClient(app) as c:
        yield c


# ---------- helpers: jobs and documents are made by the same code the assistant's tools use ----------

def _as_dict(row) -> dict:
    return row.model_dump(mode="json")


@pytest.fixture
def make_job():
    """make_job(approve=False, **fields) saves a job the way the assistant's save tool does. Returns it as a dict."""
    from sqlmodel import Session
    from app.features.jobs.schemas import JobCreate
    from app.features.jobs.services.job_service import approve_job, create_job

    def make(approve=False, **fields) -> dict:
        body = JobCreate(**{"title": "Backend Developer", "required_skills": ["Python"], **fields})
        with Session(engine) as session:
            job = create_job(session, body)
            if approve:
                job = approve_job(session, job, add_to_library=False)
            return _as_dict(job)
    return make


@pytest.fixture
def add_doc():
    """add_doc(kind, title, text) stores a company document the way the assistant's tool does. Returns it as a dict."""
    from sqlmodel import Session
    from app.features.job_library.services.company_document_service import add_document, document_out

    def add(kind, title, text) -> dict:
        with Session(engine) as session:
            return _as_dict(document_out(add_document(session, title, text, kind=kind)))
    return add
