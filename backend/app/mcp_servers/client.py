"""MCP client: reaches one of our MCP servers, calls its tools and returns their text answers.

    call_tool("app.mcp_servers.blogger_server", "publish_blog_post", {"title": ..., "text": ...})

Two ways to reach a server:
    stdio  (default)  the server runs as a short-lived child process, spoken to over standard input / output
    HTTP   (Docker)   the server is its own Docker service; its address comes from .env / docker-compose.yml
                      (MCP_BLOGGER_URL, MCP_RECRUITMENT_URL)
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from app.core import config

TIMEOUT_SEC = 45
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class McpError(Exception):
    """The MCP server could not be started, did not answer in time, or the tool failed."""


# The HTTP address of a server when it runs as a Docker service, or "" to start it as a child process
def server_url(module: str) -> str:
    return {"app.mcp_servers.blogger_server": config.MCP_BLOGGER_URL,
            "app.mcp_servers.recruitment_server": config.MCP_RECRUITMENT_URL}.get(module, "")


# Opens the connection to a server: over HTTP (Docker service) or by starting it as a child process (stdio)
@asynccontextmanager
async def _connect(module: str):
    url = server_url(module)
    if url:
        async with streamable_http_client(url) as (read, write, _):    # → the server's Docker service
            yield read, write
        return
    # The child process gets the same settings (.env values) as the backend, and can import `app`.
    environment = {**os.environ, "PYTHONPATH": BACKEND_DIR}
    parameters = StdioServerParameters(command=sys.executable, args=["-m", module], env=environment)
    async with stdio_client(parameters) as (read, write):              # → starts python -m <module>
        yield read, write


# Connects to an MCP server and calls its tools one by one (used by call_tools)
async def _call(module: str, calls: list[tuple[str, dict]]) -> list[str]:
    answers = []
    async with _connect(module) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for tool, arguments in calls:
                # → MCP: runs the tool inside the server process (e.g. publish_blog_post)
                result = await session.call_tool(tool, arguments)
                text = "".join(part.text for part in result.content if getattr(part, "type", "") == "text")
                if result.isError:
                    raise McpError(text or f"the tool {tool} reported an error")
                answers.append(text)
    return answers


def call_tools(module: str, calls: list[tuple[str, dict]], timeout: int = TIMEOUT_SEC) -> list[str]:
    """Starts the server once and calls several tools one after the other. Runs in normal (non-async) code."""
    try:
        return asyncio.run(asyncio.wait_for(_call(module, calls), timeout))
    except McpError:
        raise
    except Exception as exc:
        raise McpError(f"{type(exc).__name__} while calling the MCP server") from exc


def call_tool(module: str, tool: str, arguments: dict | None = None) -> str:
    """Calls one tool and returns its text answer."""
    return call_tools(module, [(tool, arguments or {})])[0]
