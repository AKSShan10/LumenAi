"""MCP (Model Context Protocol) servers and the client that calls them.

MCP is a standard way to offer "tools" that an application or an AI model can call.

    telegram_server.py   an MCP server with two tools: send_channel_post and check_telegram_settings
    client.py            starts a server and calls its tools

In LumenAI the backend code calls the tools, after a person clicked. The AI never chooses or calls a tool.
"""
