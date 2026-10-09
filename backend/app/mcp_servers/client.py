"""MCP client: starts one of our MCP servers, calls its tools and returns their text answers.

    call_tool("app.mcp_servers.blogger_server", "publish_blog_post", {"title": ..., "text": ...})

The server runs as a short-lived child process and is spoken to over standard input / output.
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TIMEOUT_SEC = 45
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class McpError(Exception):
    """The MCP server could not be started, did not answer in time, or the tool failed."""


async def _call(module: str, calls: list[tuple[str, dict]]) -> list[str]:
    # The child process gets the same settings (.env values) as the backend, and can import `app`.
    environment = {**os.environ, "PYTHONPATH": BACKEND_DIR}
    parameters = StdioServerParameters(command=sys.executable, args=["-m", module], env=environment)
    answers = []
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for tool, arguments in calls:
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
