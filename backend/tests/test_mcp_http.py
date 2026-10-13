"""MCP servers as their own services (the Docker way): the server answers over HTTP at /mcp and the backend
calls it by its address (MCP_EMAIL_URL). A pretend SMTP server receives the email, so nothing is really sent."""
import email
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from app.core import config
from app.mcp_servers.client import BACKEND_DIR, McpError, call_tool

SERVER = "app.mcp_servers.email_server"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def email_service(fake_smtp, monkeypatch):
    """The email MCP server started like its Docker service (MCP_HTTP_PORT set); stopped after the test."""
    port = free_port()
    env = {**os.environ, "PYTHONPATH": BACKEND_DIR, "MCP_HTTP_PORT": str(port), "MCP_ALLOWED_HOSTS": "email-mcp:*"}
    process = subprocess.Popen([sys.executable, "-m", SERVER], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(100):                                     # wait until it listens (at most ~10 s)
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    monkeypatch.setattr(config, "MCP_EMAIL_URL", url)
    yield {"url": url, "port": port, "smtp": fake_smtp}
    process.terminate()
    process.wait(timeout=10)


def test_send_email_through_the_http_service(email_service):
    answer = json.loads(call_tool(SERVER, "send_email", {"to": "asha@example.com", "subject": "Interview",
                                                         "body": "Hello Asha", "calendar": ""}))
    assert answer == {"ok": True, "error": ""}
    message = email.message_from_string(email_service["smtp"].messages[-1])
    assert message["To"] == "asha@example.com"


def test_the_settings_check_through_the_http_service(email_service):
    answer = json.loads(call_tool(SERVER, "check_email_settings"))
    assert answer["ok"] is True


def test_an_unknown_host_name_is_refused(email_service):
    """DNS rebinding protection: only the service's own name (and localhost) is accepted."""
    asked = httpx.post(email_service["url"], headers={"Host": f"evil.example:{email_service['port']}",
                                                      "Accept": "application/json, text/event-stream"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert asked.status_code == 421


def test_a_stopped_service_gives_a_plain_error(monkeypatch):
    monkeypatch.setattr(config, "MCP_EMAIL_URL", f"http://127.0.0.1:{free_port()}/mcp")   # nothing listens
    with pytest.raises(McpError):
        call_tool(SERVER, "check_email_settings")


def start_service(module: str, name: str):
    port = free_port()
    env = {**os.environ, "PYTHONPATH": BACKEND_DIR, "MCP_HTTP_PORT": str(port), "MCP_ALLOWED_HOSTS": f"{name}:*"}
    process = subprocess.Popen([sys.executable, "-m", module], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return process, f"http://127.0.0.1:{port}/mcp"


def test_the_assistant_gets_its_tools_from_the_http_services(monkeypatch):
    import asyncio
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from app.graphs.assistant_agent import mcp_servers
    recruitment, recruitment_url = start_service("app.mcp_servers.recruitment_server", "recruitment-mcp")
    blogger, blogger_url = start_service("app.mcp_servers.blogger_server", "blogger-mcp")
    try:
        monkeypatch.setattr(config, "MCP_RECRUITMENT_URL", recruitment_url)
        monkeypatch.setattr(config, "MCP_BLOGGER_URL", blogger_url)
        servers = mcp_servers()
        assert servers["recruitment"] == {"url": recruitment_url, "transport": "streamable_http"}
        names = {t.name for t in asyncio.run(MultiServerMCPClient(servers).get_tools())}
        assert {"list_jobs", "publish_blog_post"} <= names
    finally:
        for process in (recruitment, blogger):
            process.terminate()
            process.wait(timeout=10)
