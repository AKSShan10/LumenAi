"""MCP client: the one place that knows our MCP servers, and calls one tool on them.

    mcp_servers()                                   where each server is: used here and by the assistant agent
    call_tool("blogger", "check_blogger_settings")  backend code calls one tool by name and gets its text answer

Two ways to reach a server:
    stdio  (default)  the server is started as a short-lived child process: python -m app.mcp_servers.<name>_server
    HTTP   (Docker)   the server is its own Docker service; its address is MCP_BLOGGER_URL / MCP_RECRUITMENT_URL
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from app.core import config

TIMEOUT_SEC = 45
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class McpError(Exception):
    """The MCP server could not be started, did not answer in time, or the tool failed."""


def mcp_servers() -> dict:
    """Our two MCP servers. An address in .env means its Docker service (HTTP); no address means a child process."""
    environment = {**os.environ, "PYTHONPATH": BACKEND_DIR}      # the child gets the backend's settings, can import app
    servers = {}
    for name, url in (("recruitment", config.MCP_RECRUITMENT_URL), ("blogger", config.MCP_BLOGGER_URL)):
        if url:
            servers[name] = {"url": url, "transport": "streamable_http"}
        else:
            servers[name] = {"command": sys.executable, "args": ["-m", f"app.mcp_servers.{name}_server"],
                             "transport": "stdio", "env": environment}
    return servers


async def _call(server: dict, tool: str, arguments: dict) -> str:
    """Connects to one server, runs one tool, returns its text answer."""
    if server["transport"] == "streamable_http":
        connection = streamable_http_client(server["url"])                # → the server's Docker service
    else:
        connection = stdio_client(StdioServerParameters(command=server["command"], args=server["args"],
                                                        env=server["env"]))  # → starts python -m <server>
    async with connection as streams:
        read, write = streams[0], streams[1]          # HTTP also gives a third value, which is not needed
        async with ClientSession(read, write) as session:
            await session.initialize()                                      # MCP hello: client and server agree
            result = await session.call_tool(tool, arguments)               # → runs the tool inside the server
    text = "".join(part.text for part in result.content if getattr(part, "type", "") == "text")
    if result.isError:
        raise McpError(text or f"the tool {tool} reported an error")
    return text


def call_tool(name: str, tool: str, arguments: dict | None = None) -> str:
    """Calls one tool on the server "blogger" or "recruitment" from normal (non-async) code. Waits at most 45 s."""
    server = mcp_servers()[name]
    try:
        return asyncio.run(asyncio.wait_for(_call(server, tool, arguments or {}), TIMEOUT_SEC))
    except McpError:
        raise
    except Exception as exc:                          # not started, no answer in time, connection refused ...
        raise McpError(f"{type(exc).__name__} while calling the MCP server") from exc
