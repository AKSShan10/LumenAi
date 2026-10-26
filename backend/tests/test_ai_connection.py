"""Tests for the AI connection messages: the screen must say WHY the AI failed, in plain words.
A tiny local server plays the AI service, so no real key or internet is needed."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.ai import llm_client
from app.core import config


class FakeAIService(BaseHTTPRequestHandler):
    """Answers like Gemini's own address (".../models/<model>:generateContent") or the OpenAI-style one."""
    status = 200            # the HTTP status the fake service answers with
    content = '{"ok": true}'
    replies: list = []      # if set, the next answers in order (then "content" again)
    statuses: list = []     # if set, the HTTP status of the next answers in order (then "status" again)
    usage = {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 45, "totalTokenCount": 195}
    calls = 0
    paths: list = []

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        FakeAIService.calls += 1
        FakeAIService.paths.append(self.path)
        if FakeAIService.replies:
            self.content = FakeAIService.replies.pop(0)
        if FakeAIService.statuses:
            self.status = FakeAIService.statuses.pop(0)
        if self.status == 200 and self.path.endswith(":generateContent"):
            body = {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [
                {"text": "Let me think about the title.", "thought": True},     # a thinking note: not the answer
                {"text": self.content}]}}], "usageMetadata": self.usage}
        elif self.status == 200:
            body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": self.content}}]}
        else:
            body = {"error": {"message": "fake error", "type": "error", "code": self.status}}
        data = json.dumps(body).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def ai_service(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeAIService)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setattr(config, "LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1beta/openai/")
    monkeypatch.setattr(llm_client, "RETRY_WAITS", (0, 0, 0, 0))     # no real waiting in tests
    FakeAIService.status, FakeAIService.content = 200, '{"ok": true}'
    FakeAIService.replies, FakeAIService.statuses, FakeAIService.calls, FakeAIService.paths = [], [], 0, []
    yield FakeAIService
    server.shutdown()


def test_working_service(ai_service):
    assert llm_client.check_connection()["ok"] is True


def test_json_inside_code_fences_is_read(ai_service):
    ai_service.content = '```json\n{"title": "Backend Engineer"}\n```'
    assert llm_client.llm_json("Write a title.", "x") == {"title": "Backend Engineer"}


def test_answer_that_is_not_json(ai_service):
    ai_service.content = "Sorry, I cannot do that."
    assert llm_client.llm_json("Write a title.", "x") is None
    assert "not with valid JSON" in llm_client.last_error()
    assert ai_service.calls == 2                       # asked once more before giving up


def test_broken_json_is_asked_once_more(ai_service):
    ai_service.replies = ['{"title": "Backend "Engineer"}', '{"title": "Backend Engineer"}']   # 1st: bad quote
    assert llm_client.llm_json("Write a title.", "x") == {"title": "Backend Engineer"}
    assert ai_service.calls == 2


@pytest.mark.parametrize("status, words", [(401, "API key"), (404, "model name")])
def test_failure_reason_is_shown(ai_service, status, words):
    ai_service.status = status
    result = llm_client.check_connection()
    assert result["ok"] is False and words in result["message"]


def test_gemini_uses_its_own_address_and_logs_the_thinking(ai_service, caplog):
    caplog.set_level("INFO", logger="llm")
    ai_service.content = '{"title": "Backend Engineer"}'
    assert llm_client.llm_json("Write a title.", "x") == {"title": "Backend Engineer"}   # the thinking note is skipped
    assert ai_service.paths == ["/v1beta/models/gemini-3.5-flash-lite:generateContent"]
    assert "tokens in=120 out=30 thinking=45" in caplog.text


def test_too_many_requests_waits_and_tries_again(ai_service):
    ai_service.statuses = [429, 503]                   # busy twice, then a normal answer
    ai_service.content = '{"title": "Backend Engineer"}'
    assert llm_client.llm_json("Write a title.", "x") == {"title": "Backend Engineer"}
    assert ai_service.calls == 3


def test_other_providers_keep_the_openai_address(ai_service, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    ai_service.content = '{"title": "Backend Engineer"}'
    assert llm_client.llm_json("Write a title.", "x") == {"title": "Backend Engineer"}
    assert ai_service.paths == ["/v1beta/openai/chat/completions"]


def test_placeholder_key_is_caught(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "LLM_API_KEY", "replace-me")
    assert "LLM_API_KEY is not set" in llm_client.check_connection()["message"]


def test_check_endpoint(client):
    body = client.get("/api/llm-check").json()
    assert body["ok"] is True and body["provider"] == "fake"       # fake AI in the test settings


def test_health_names_the_ai_provider(client):
    assert client.get("/api/health").json()["llm"] == "fake"
