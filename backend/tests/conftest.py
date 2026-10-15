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
    "STT_PROVIDER": "fake",               # test sentences instead of Deepgram
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


# ---------- a pretend email server for the invitation tests (nothing leaves this computer) ----------

class FakeSmtpServer:
    """A tiny SMTP server on 127.0.0.1 that accepts every login and keeps each email it receives (as raw text)."""

    def __init__(self):
        import socket
        import threading
        self.messages: list[str] = []
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(5)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return                                  # closed at the end of the test
            with connection, connection.makefile("rb") as lines:
                send = lambda text: connection.sendall(text.encode() + b"\r\n")   # noqa: E731
                send("220 fake smtp ready")
                for raw in lines:
                    command = raw.decode(errors="ignore").strip().upper()
                    if command.startswith("EHLO"):
                        send("250-fake\r\n250-AUTH PLAIN LOGIN\r\n250 OK")
                    elif command.startswith("AUTH"):
                        send("235 OK")
                    elif command.startswith("DATA"):
                        send("354 go on")
                        data = []
                        for line in lines:
                            if line in (b".\r\n", b".\n"):
                                break
                            data.append(line.decode(errors="ignore"))
                        self.messages.append("".join(data))
                        send("250 kept")
                    elif command.startswith("QUIT"):
                        send("221 bye")
                        break
                    else:                                # HELO, MAIL, RCPT, RSET, NOOP
                        send("250 OK")

    def close(self):
        self.listener.close()


@pytest.fixture
def fake_smtp(monkeypatch):
    """SMTP settings that point to the pretend server, for this process and for the MCP server it starts."""
    from app.core import config
    server = FakeSmtpServer()
    settings = {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(server.port), "SMTP_USER": "hr@example.com",
                "SMTP_PASSWORD": "made-up-password", "SMTP_FROM": "hr@example.com", "SMTP_STARTTLS": "false"}
    for name, value in settings.items():
        monkeypatch.setenv(name, value)                  # the MCP server is a child process: it reads the environment
        monkeypatch.setattr(config, name, int(value) if name == "SMTP_PORT" else value)
    monkeypatch.setattr(config, "SMTP_STARTTLS", False)
    yield server
    server.close()
