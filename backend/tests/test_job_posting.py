"""Posting an approved job to the Telegram channel: the AI writes the post, a person posts it."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.features.jobs.services import job_posting_service
from app.graphs import job_post_graph as workflow
from app.graphs.job_post_graph import find_post_problems
from app.graphs.job_post_prompts import JOB_POST_PROMPT, JOB_POST_REVISE_PROMPT
from app.mcp_servers.client import McpError, call_tool

FORM = "https://docs.google.com/forms/d/e/made-up-form/viewform"
DESCRIPTION = "We are looking for a Backend Developer who builds REST APIs with Python and FastAPI for our products."
JOB = {"title": "Backend Developer", "required_skills": ["Python", "FastAPI"], "preferred_skills": ["Docker"],
       "min_years": 3, "qualifications": "BSc in CSE", "description": DESCRIPTION}
GOOD_POST = ("Backend Developer\n\n" + "We are hiring a careful engineer who enjoys building reliable services. " * 4
             + "\n- Python\n- FastAPI")


@pytest.fixture
def approved_job(client) -> dict:
    job = client.post("/api/jobs", json=JOB).json()
    return client.post(f"/api/jobs/{job['id']}/approve", json={"add_to_library": False}).json()


# ---------- the check (plain Python rules) ----------

def test_the_check_finds_plain_problems():
    assert find_post_problems(GOOD_POST, JOB) == []
    assert "too short" in " ".join(find_post_problems("Backend Developer wanted", JOB))
    assert "job title" in " ".join(find_post_problems(GOOD_POST.replace("Backend Developer", "Engineer"), JOB))
    assert "link" in " ".join(find_post_problems(GOOD_POST + " https://example.com", JOB))
    assert "pay" in " ".join(find_post_problems(GOOD_POST + " Salary 50000 BDT.", JOB))
    assert find_post_problems(GOOD_POST + " Salary 50000 BDT.", {**JOB, "description": "Salary: 50000 BDT"}) == []


def test_steps_of_the_workflow():
    steps = [name for name in workflow.job_post_graph.get_graph().nodes if not name.startswith("__")]
    assert steps == ["write_post", "check_post", "revise_post", "log_run"]


# ---------- the post made by code from the approved job ----------

def test_the_default_post_is_the_approved_description(client, approved_job, monkeypatch):
    monkeypatch.setattr(workflow, "llm_json", lambda instructions, data: 1 / 0)      # the AI must not be called
    text = client.get(f"/api/jobs/{approved_job['id']}/post-text").json()["text"]
    assert text.startswith("Backend Developer\n\n" + DESCRIPTION)
    assert "Required skills: Python, FastAPI" in text and "Nice to have: Docker" in text
    assert "Experience: 3+ years" in text and "Qualifications: BSc in CSE" in text


# ---------- the optional shorter post, written by the AI ----------

def test_ai_writes_the_post_and_nothing_is_posted(client, approved_job):
    draft = client.post(f"/api/jobs/{approved_job['id']}/post-draft").json()
    assert draft["from_ai"] is True and draft["message"] == ""
    assert "Backend Developer" in draft["text"] and "Python" in draft["text"]
    assert "http" not in draft["text"]                                  # the link is added by code, not by the AI
    assert client.get(f"/api/jobs/{approved_job['id']}/postings").json() == []


def test_a_bad_post_goes_back_to_the_ai_once(client, approved_job, monkeypatch):
    asked = []

    def ai(instructions, data):
        asked.append(instructions)
        return {"text": "Too short"} if instructions == JOB_POST_PROMPT else {"text": GOOD_POST}
    monkeypatch.setattr(workflow, "llm_json", ai)
    draft = client.post(f"/api/jobs/{approved_job['id']}/post-draft").json()
    assert asked == [JOB_POST_PROMPT, JOB_POST_REVISE_PROMPT]
    assert draft["text"] == GOOD_POST and draft["message"] == ""


def test_generate_again_passes_the_wish_to_the_ai(client, approved_job, monkeypatch):
    first = client.post(f"/api/jobs/{approved_job['id']}/post-draft").json()["text"]
    seen = {}

    def ai(instructions, data):
        seen.update(data)
        return {"text": GOOD_POST}
    monkeypatch.setattr(workflow, "llm_json", ai)
    client.post(f"/api/jobs/{approved_job['id']}/post-draft",
                json={"change_request": "shorter and friendlier", "previous": first})
    assert seen["change_request"] == "shorter and friendlier" and seen["previous_post"] == first


def test_ai_failure_is_reported(client, approved_job, monkeypatch):
    monkeypatch.setattr(workflow, "llm_json", lambda instructions, data: None)
    draft = client.post(f"/api/jobs/{approved_job['id']}/post-draft").json()
    assert draft["from_ai"] is False and "could not write the post" in draft["message"]


# ---------- posting ----------

def test_post_goes_through_the_mcp_tool_and_is_saved(client, approved_job):
    """With TELEGRAM_PROVIDER=fake the real MCP server is started, but nothing leaves this computer."""
    posting = client.post(f"/api/jobs/{approved_job['id']}/post", json={"text": GOOD_POST, "apply_url": FORM}).json()
    assert posting["status"] == "posted" and posting["error"] == "" and posting["apply_url"] == FORM
    saved = client.get(f"/api/jobs/{approved_job['id']}/postings").json()
    assert [p["id"] for p in saved] == [posting["id"]]


def test_the_link_is_added_by_code(client, approved_job, monkeypatch):
    sent = {}

    def tool(server, name, arguments=None):
        sent.update(arguments, tool=name)
        return json.dumps({"ok": True, "message_id": 7, "link": "https://t.me/made_up_channel/7", "error": ""})
    monkeypatch.setattr(job_posting_service, "call_tool", tool)
    posting = client.post(f"/api/jobs/{approved_job['id']}/post", json={"text": GOOD_POST, "apply_url": FORM}).json()
    assert sent["tool"] == "send_channel_post"
    assert sent["text"].endswith(f"Apply here: {FORM}") and sent["button_url"] == FORM
    assert posting["message_link"] == "https://t.me/made_up_channel/7"


def test_a_failed_post_is_saved_with_the_reason(client, approved_job, monkeypatch):
    def refuse(server, name, arguments=None):
        return json.dumps({"ok": False, "message_id": 0, "link": "", "error": "Forbidden: bot is not a member of the channel chat"})
    monkeypatch.setattr(job_posting_service, "call_tool", refuse)
    posting = client.post(f"/api/jobs/{approved_job['id']}/post", json={"text": GOOD_POST, "apply_url": FORM}).json()
    assert posting["status"] == "failed" and "not a member" in posting["error"]

    def broken(server, name, arguments=None):
        raise McpError("TimeoutError while calling the MCP server")
    monkeypatch.setattr(job_posting_service, "call_tool", broken)
    posting = client.post(f"/api/jobs/{approved_job['id']}/post", json={"text": GOOD_POST, "apply_url": FORM}).json()
    assert posting["status"] == "failed" and "did not answer" in posting["error"]


def test_only_an_approved_job_can_be_posted(client):
    draft = client.post("/api/jobs", json=JOB).json()
    assert client.post(f"/api/jobs/{draft['id']}/post-draft").status_code == 400
    assert client.post(f"/api/jobs/{draft['id']}/post", json={"text": GOOD_POST, "apply_url": FORM}).status_code == 400
    assert client.get(f"/api/jobs/{draft['id']}/post-text").status_code == 400
    assert client.get(f"/api/jobs/{draft['id']}/postings").json() == []


def test_bad_input_is_rejected(client, approved_job):
    url = f"/api/jobs/{approved_job['id']}/post"
    assert client.post(url, json={"text": GOOD_POST, "apply_url": "not a link"}).status_code == 422
    assert client.post(url, json={"text": GOOD_POST, "apply_url": "http://insecure.example.com/form"}).status_code == 422
    assert client.post(url, json={"text": "short", "apply_url": FORM}).status_code == 422
    assert client.post("/api/jobs/999999/post", json={"text": GOOD_POST, "apply_url": FORM}).status_code == 404


def test_posting_needs_login(anonymous):
    assert anonymous.post("/api/jobs/1/post", json={"text": GOOD_POST, "apply_url": FORM}).status_code == 401
    assert anonymous.post("/api/jobs/1/post-draft").status_code == 401
    assert anonymous.get("/api/jobs/1/post-text").status_code == 401
    assert anonymous.get("/api/telegram-check").status_code == 401


def test_settings_check(client):
    answer = client.get("/api/telegram-check").json()
    assert answer["ok"] is True and "Fake Telegram" in answer["message"]


# ---------- the real Telegram path, against a tiny local server that plays Telegram ----------

class PretendTelegram(BaseHTTPRequestHandler):
    calls = []          # (path, body) of every request it got

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        PretendTelegram.calls.append((self.path, body))
        if "/botgood-token/" not in self.path:
            answer = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        elif self.path.endswith("/sendMessage"):
            answer = {"ok": True, "result": {"message_id": 42, "chat": {"id": -100123, "username": "made_up_channel"}}}
        elif self.path.endswith("/getMe"):
            answer = {"ok": True, "result": {"username": "made_up_bot"}}
        else:
            answer = {"ok": True, "result": {"title": "Made-up Jobs"}}
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):          # keep the test output quiet
        pass


@pytest.fixture
def pretend_telegram(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), PretendTelegram)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    PretendTelegram.calls.clear()
    # The MCP server is a child process: it reads these settings when it starts.
    monkeypatch.setenv("TELEGRAM_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@made_up_channel")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "good-token")
    yield monkeypatch
    server.shutdown()


def test_mcp_server_posts_to_telegram(pretend_telegram):
    answer = json.loads(call_tool("app.mcp_servers.telegram_server", "send_channel_post",
                                  {"text": "Backend Developer", "button_text": "Apply now", "button_url": FORM}))
    assert answer == {"ok": True, "message_id": 42, "link": "https://t.me/made_up_channel/42", "error": ""}
    path, body = PretendTelegram.calls[-1]
    assert path.endswith("/sendMessage") and body["chat_id"] == "@made_up_channel" and body["text"] == "Backend Developer"
    assert body["reply_markup"]["inline_keyboard"][0][0] == {"text": "Apply now", "url": FORM}

    check = json.loads(call_tool("app.mcp_servers.telegram_server", "check_telegram_settings"))
    assert check["ok"] is True and "made_up_bot" in check["message"] and "Made-up Jobs" in check["message"]


def test_a_wrong_token_is_explained_and_never_shown(pretend_telegram):
    pretend_telegram.setenv("TELEGRAM_BOT_TOKEN", "wrong-token")
    answer = json.loads(call_tool("app.mcp_servers.telegram_server", "send_channel_post", {"text": "Backend Developer"}))
    assert answer["ok"] is False and answer["error"] == "Unauthorized"
    check = json.loads(call_tool("app.mcp_servers.telegram_server", "check_telegram_settings"))
    assert check["ok"] is False and "token was not accepted" in check["message"] and "wrong-token" not in check["message"]

    pretend_telegram.setenv("TELEGRAM_API_URL", "http://127.0.0.1:1")           # nothing listens there
    answer = json.loads(call_tool("app.mcp_servers.telegram_server", "send_channel_post", {"text": "Backend Developer"}))
    assert answer["ok"] is False and "could not reach Telegram" in answer["error"] and "wrong-token" not in answer["error"]

    pretend_telegram.setenv("TELEGRAM_BOT_TOKEN", "")
    answer = json.loads(call_tool("app.mcp_servers.telegram_server", "send_channel_post", {"text": "Backend Developer"}))
    assert answer["error"] == "TELEGRAM_BOT_TOKEN is missing in .env"
