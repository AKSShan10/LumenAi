"""MCP servers as their own services (the Docker way): the server answers over HTTP at /mcp and the backend
calls it by its address (MCP_BLOGGER_URL). Fake Blogger (BLOGGER_PROVIDER=fake), so nothing is really published."""
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

SERVER = "app.mcp_servers.blogger_server"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def blogger_service(monkeypatch):
    """The Blogger MCP server started like its Docker service (MCP_HTTP_PORT set); stopped after the test."""
    process, url = start_service(SERVER, "blogger-mcp")
    monkeypatch.setattr(config, "MCP_BLOGGER_URL", url)
    yield {"url": url, "port": int(url.split(":")[2].split("/")[0])}
    process.terminate()
    process.wait(timeout=10)


def test_publish_through_the_http_service(blogger_service):
    answer = json.loads(call_tool(SERVER, "publish_blog_post", {"title": "Backend Developer", "text": "We are hiring."}))
    assert answer == {"ok": True, "link": "", "error": ""}


def test_the_settings_check_through_the_http_service(blogger_service):
    answer = json.loads(call_tool(SERVER, "check_blogger_settings"))
    assert answer["ok"] is True


def test_an_unknown_host_name_is_refused(blogger_service):
    """DNS rebinding protection: only the service's own name (and localhost) is accepted."""
    asked = httpx.post(blogger_service["url"], headers={"Host": f"evil.example:{blogger_service['port']}",
                                                        "Accept": "application/json, text/event-stream"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert asked.status_code == 421


def test_a_stopped_service_gives_a_plain_error(monkeypatch):
    monkeypatch.setattr(config, "MCP_BLOGGER_URL", f"http://127.0.0.1:{free_port()}/mcp")   # nothing listens
    with pytest.raises(McpError):
        call_tool(SERVER, "check_blogger_settings")


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
