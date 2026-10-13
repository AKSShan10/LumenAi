"""The email MCP server. It offers two tools:

    send_email(to, subject, body, calendar)   sends one email; calendar = the text of an .ics invite (may be empty)
    check_email_settings()                    checks the SMTP settings and the login, sends nothing

The backend starts it when the interviewer clicks "Send email":   python -m app.mcp_servers.email_server
It talks over standard input / output (the "stdio" transport), so it needs no port and no extra container.
Any other MCP client can use the same server, for example the MCP Inspector:
    npx @modelcontextprotocol/inspector python -m app.mcp_servers.email_server

The server reads SMTP_* from the environment. The password never leaves this process.
"""
import json

from mcp.server.fastmcp import FastMCP

from app.features.interviews.services import smtp_service
from app.mcp_servers.serve import serve

server = FastMCP("lumenai-email")


@server.tool()
def send_email(to: str, subject: str, body: str, calendar: str = "") -> str:
    """Send one email, with an optional calendar invite (.ics text) that mail apps show as an event.
    Returns JSON: {"ok": true/false, "error": "..."}."""
    return json.dumps(smtp_service.send_email(to, subject, body, calendar))


@server.tool()
def check_email_settings() -> str:
    """Check the SMTP settings and the login without sending. Returns JSON: {"ok": true/false, "message": "..."}."""
    return json.dumps(smtp_service.check_email_settings())


if __name__ == "__main__":
    serve(server)         # stdio, or an HTTP service in Docker (mcp_servers/serve.py)
