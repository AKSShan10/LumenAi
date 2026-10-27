"""Starts one of our MCP servers in the right way:

    stdio (default)   the backend starts the server as a short-lived child process and talks to it over standard
                      input / output (tests, and running without Docker)
    HTTP (Docker)     MCP_HTTP_PORT is set: the server runs as its own Docker service and answers at
                      http://<service>:<port>/mcp ("streamable HTTP"). The backend calls it by that address.

MCP_ALLOWED_HOSTS lists the host names the HTTP server answers to (for example "blogger-mcp:*"). Any other
host name is refused, so a web page cannot trick a browser into calling the server (DNS rebinding protection).
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


# Runs the server over stdio, or as an HTTP service when MCP_HTTP_PORT is set (Docker)
def serve(server: FastMCP) -> None:
    # The tools call the AI too (for example write_job_draft), so the server writes to the app's one log file:
    # the AI calls with their tokens, in the same time zone. The backend starts new files; this server only adds
    # lines (rotate=False). (The terminal part goes to stderr, so it never mixes with the stdio messages on stdout.)
    from app.core import config
    from app.core.logging_setup import setup_logging
    setup_logging(config.LOG_FILE, config.LOG_TIME_ZONE, rotate=False)
    port = os.getenv("MCP_HTTP_PORT", "")
    if not port:
        server.run()                                  # stdio transport
        return
    hosts = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    server.settings.host, server.settings.port = "0.0.0.0", int(port)     # reachable from the other containers
    server.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts + ["127.0.0.1:*", "localhost:*"],
        allowed_origins=[],
    )
    server.run(transport="streamable-http")          # → answers at http://0.0.0.0:<port>/mcp
