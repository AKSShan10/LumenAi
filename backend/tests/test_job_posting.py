"""Posting an approved job to the blog (Blogger): the backend posts it through an MCP tool, after a Yes in the chat."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.core.database import engine
from app.features.jobs.models import Job
from app.features.jobs.services import job_posting_service
from app.features.jobs.services.job_posting_service import approved_post, post_job
from app.mcp_servers.client import McpError, call_tool

FORM = "https://docs.google.com/forms/d/e/made-up-form/viewform"
DESCRIPTION = "We are looking for a Backend Developer who builds REST APIs with Python and FastAPI for our products."
JOB = {"title": "Backend Developer", "required_skills": ["Python", "FastAPI"], "preferred_skills": ["Docker"],
       "min_years": 3, "qualifications": "BSc in CSE", "description": DESCRIPTION}
GOOD_POST = ("Backend Developer\n\n" + "We are hiring a careful engineer who enjoys building reliable services. " * 4
             + "\n- Python\n- FastAPI")


@pytest.fixture
def approved_job(make_job) -> dict:
    return make_job(approve=True, **JOB)


def post(job_id: int, text: str = GOOD_POST, apply_url: str = FORM) -> dict:
    """Posts the way the backend does after a Yes in the chat. Returns the saved posting."""
    with Session(engine) as session:
        return post_job(session, session.get(Job, job_id), text, apply_url).model_dump(mode="json")


# ---------- the post made by code from the approved job ----------

def test_the_post_is_the_approved_description(approved_job):
    with Session(engine) as session:
        text = approved_post(session.get(Job, approved_job["id"]))
    assert text.startswith("Backend Developer\n\n" + DESCRIPTION)
    assert "Required skills: Python, FastAPI" in text and "Nice to have: Docker" in text
    assert "Experience: 3+ years" in text and "Qualifications: BSc in CSE" in text


# ---------- posting ----------

def test_post_goes_through_the_mcp_tool_and_is_saved(client, approved_job):
    """With BLOGGER_PROVIDER=fake the real MCP server is started, but nothing leaves this computer."""
    posting = post(approved_job["id"])
    assert posting["channel"] == "blogger"
    assert posting["status"] == "posted" and posting["error"] == "" and posting["apply_url"] == FORM
    saved = client.get(f"/api/jobs/{approved_job['id']}/postings").json()           # the list on the page shows it
    assert [p["id"] for p in saved] == [posting["id"]]


def test_the_blog_post_gets_the_job_title_and_the_link(approved_job, monkeypatch):
    sent = {}

    def tool(server, name, arguments=None):
        sent.update(arguments, tool=name, server=server)
        return json.dumps({"ok": True, "link": "https://made-up.blogspot.com/2026/10/backend-developer.html", "error": ""})
    monkeypatch.setattr(job_posting_service, "call_tool", tool)
    posting = post(approved_job["id"])
    assert sent["server"] == "blogger" and sent["tool"] == "publish_blog_post"
    assert sent["title"] == approved_job["title"] and sent["text"] == GOOD_POST and sent["button_url"] == FORM
    assert posting["message_link"].startswith("https://made-up.blogspot.com/")


def test_a_failed_post_is_saved_with_the_reason(approved_job, monkeypatch):
    def refuse(server, name, arguments=None):
        return json.dumps({"ok": False, "link": "", "error": "The caller does not have permission"})
    monkeypatch.setattr(job_posting_service, "call_tool", refuse)
    posting = post(approved_job["id"])
    assert posting["status"] == "failed" and "permission" in posting["error"]

    def broken(server, name, arguments=None):
        raise McpError("TimeoutError while calling the MCP server")
    monkeypatch.setattr(job_posting_service, "call_tool", broken)
    posting = post(approved_job["id"])
    assert posting["status"] == "failed" and "did not answer" in posting["error"]


def test_only_an_approved_job_can_be_posted(client, make_job):
    draft = make_job(**JOB)
    with pytest.raises(HTTPException):
        post(draft["id"])
    assert client.get(f"/api/jobs/{draft['id']}/postings").json() == []


def test_posting_is_not_possible_through_the_api(client, approved_job):
    """A post is asked for in the chat and sent after a Yes. The old button endpoints are gone."""
    job_id = approved_job["id"]
    assert client.post(f"/api/jobs/{job_id}/post", json={"text": GOOD_POST, "apply_url": FORM}).status_code == 404
    assert client.post(f"/api/jobs/{job_id}/post-draft").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/post-text").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/postings").json() == []
    assert client.get("/api/jobs/999999/postings").status_code == 404


def test_posting_needs_login(anonymous):
    assert anonymous.get("/api/jobs/1/postings").status_code == 401
    assert anonymous.get("/api/posting-check").status_code == 401


def test_settings_check(client):
    answer = client.get("/api/posting-check").json()
    assert answer["ok"] is True and "Fake Blogger" in answer["message"]


# ---------- the real Blogger path, against a tiny local server that plays Google ----------

class PretendGoogle(BaseHTTPRequestHandler):
    calls = []                 # (path, body, Authorization header)

    def _reply(self, status, answer):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(answer).encode())

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        PretendGoogle.calls.append((self.path, body, self.headers.get("Authorization", "")))
        if self.path == "/token":                                   # swap the refresh token for an access token
            if "refresh_token=good-refresh" in body:
                return self._reply(200, {"access_token": "access-123"})
            return self._reply(400, {"error": "invalid_grant"})
        if self.headers.get("Authorization") != "Bearer access-123":
            return self._reply(401, {"error": {"message": "Invalid Credentials"}})
        if self.path == "/blogs/42/posts/":
            return self._reply(200, {"id": "7654321098765432109", "url": "https://made-up.blogspot.com/2026/10/job.html"})
        self._reply(404, {"error": {"message": "Not Found"}})

    def do_GET(self):
        PretendGoogle.calls.append((self.path, "", self.headers.get("Authorization", "")))
        if self.path == "/blogs/42":
            return self._reply(200, {"id": "42", "name": "Made-up Careers"})
        self._reply(404, {"error": {"message": "Not Found"}})

    def log_message(self, *args):
        pass


@pytest.fixture()
def pretend_google(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), PretendGoogle)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    PretendGoogle.calls.clear()
    address = f"http://127.0.0.1:{server.server_port}"
    # the MCP server is a child process: it reads these when it starts
    for name, value in {"BLOGGER_PROVIDER": "blogger", "BLOGGER_API_URL": address, "GOOGLE_TOKEN_URL": address + "/token",
                        "BLOGGER_BLOG_ID": "42", "BLOGGER_CLIENT_ID": "made-up-client",
                        "BLOGGER_CLIENT_SECRET": "made-up-secret", "BLOGGER_REFRESH_TOKEN": "good-refresh"}.items():
        monkeypatch.setenv(name, value)
    yield monkeypatch
    server.shutdown()


BLOGGER = "blogger"


def test_mcp_server_publishes_on_blogger(pretend_google):
    answer = json.loads(call_tool(BLOGGER, "publish_blog_post",
                                  {"title": "Backend Developer", "text": "Line one <b>\nLine two",
                                   "button_text": "Apply now", "button_url": FORM}))
    assert answer == {"ok": True, "link": "https://made-up.blogspot.com/2026/10/job.html", "error": ""}
    path, body, login = PretendGoogle.calls[-1]
    sent = json.loads(body)
    assert path == "/blogs/42/posts/" and login == "Bearer access-123" and sent["title"] == "Backend Developer"
    assert "Line one &lt;b&gt;<br>" in sent["content"]                       # the text is escaped, line breaks are kept
    assert f'<a href="{FORM}"><b>Apply now</b></a>' in sent["content"]       # the link is added by code

    check = json.loads(call_tool(BLOGGER, "check_blogger_settings"))
    assert check["ok"] is True and "Made-up Careers" in check["message"]


def test_blogger_problems_are_explained_and_secrets_never_shown(pretend_google):
    pretend_google.setenv("BLOGGER_REFRESH_TOKEN", "old-refresh")
    answer = json.loads(call_tool(BLOGGER, "publish_blog_post", {"title": "Backend Developer", "text": "Made-up text"}))
    assert answer["ok"] is False and "blogger_login.py" in answer["error"]
    assert "old-refresh" not in answer["error"] and "made-up-secret" not in answer["error"]

    pretend_google.setenv("BLOGGER_REFRESH_TOKEN", "good-refresh")
    pretend_google.setenv("BLOGGER_BLOG_ID", "999")                           # a blog that does not exist
    check = json.loads(call_tool(BLOGGER, "check_blogger_settings"))
    assert check["ok"] is False and "Check BLOGGER_BLOG_ID" in check["message"]

    pretend_google.setenv("GOOGLE_TOKEN_URL", "http://127.0.0.1:1/token")     # nothing listens there
    answer = json.loads(call_tool(BLOGGER, "publish_blog_post", {"title": "Backend Developer", "text": "Made-up text"}))
    assert answer["ok"] is False and "could not reach Google" in answer["error"] and "good-refresh" not in answer["error"]

    pretend_google.setenv("BLOGGER_BLOG_ID", "")
    answer = json.loads(call_tool(BLOGGER, "publish_blog_post", {"title": "Backend Developer", "text": "Made-up text"}))
    assert answer["error"] == "BLOGGER_BLOG_ID is missing in .env"
