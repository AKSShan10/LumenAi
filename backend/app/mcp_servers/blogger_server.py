"""The Blogger MCP server. It offers two tools:

    publish_blog_post(title, text, button_text, button_url)   publishes one post on the blog set in .env
    check_blogger_settings()                                  asks Google about the login and the blog, publishes nothing

Who calls it:
    job_posting_service   call_tool("blogger", "publish_blog_post", ...) after a person's Yes, and the Settings check
    assistant agent       gets only check_blogger_settings (publish_blog_post is hidden, see HIDDEN_TOOLS)
How it runs (app/mcp_servers/client.py): a child process over stdio, or the blogger-mcp Docker service over HTTP.
Any other MCP client can use the same server, for example the MCP Inspector:
    npx @modelcontextprotocol/inspector python -m app.mcp_servers.blogger_server

The server reads BLOGGER_* from the environment. The Google login values never leave this process.
"""
import json

from mcp.server.fastmcp import FastMCP

from app.features.jobs.services.blogger_service import blogger_check, blogger_publish
from app.mcp_servers.serve import serve

server = FastMCP("lumenai-blogger")


@server.tool()
def publish_blog_post(title: str, text: str, button_text: str = "", button_url: str = "") -> str:
    """Publish one post on the blog, with an optional link under it.
    Returns JSON: {"ok": true/false, "link": "...", "error": "..."}."""
    return json.dumps(blogger_publish(title, text, button_text, button_url))


@server.tool()
def check_blogger_settings() -> str:
    """Check the Google login and the blog without publishing. Returns JSON: {"ok": true/false, "message": "..."}."""
    return json.dumps(blogger_check())


if __name__ == "__main__":
    serve(server)         # stdio, or an HTTP service in Docker (mcp_servers/serve.py)
