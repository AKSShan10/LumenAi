"""The Telegram MCP server. It offers two tools:

    send_channel_post(text, button_text, button_url)   posts one message to the channel set in .env
    check_telegram_settings()                          asks Telegram about the bot and the channel, posts nothing

The backend starts it when it has something to post:   python -m app.mcp_servers.telegram_server
It talks over standard input / output (the "stdio" transport), so it needs no port and no extra container.
Any other MCP client can use the same server, for example the MCP Inspector:
    npx @modelcontextprotocol/inspector python -m app.mcp_servers.telegram_server

The server reads TELEGRAM_* from the environment. The bot token never leaves this process.
"""
import json

from mcp.server.fastmcp import FastMCP

from app.features.jobs.services.telegram_service import telegram_check, telegram_send

server = FastMCP("lumenai-telegram")


@server.tool()
def send_channel_post(text: str, button_text: str = "", button_url: str = "") -> str:
    """Post one message to the channel, with an optional link button under it.
    Returns JSON: {"ok": true/false, "message_id": 0, "link": "...", "error": "..."}."""
    return json.dumps(telegram_send(text, button_text, button_url))


@server.tool()
def check_telegram_settings() -> str:
    """Check the bot token and the channel without posting. Returns JSON: {"ok": true/false, "message": "..."}."""
    return json.dumps(telegram_check())


if __name__ == "__main__":
    server.run()          # stdio transport
