"""MCP (Model Context Protocol) servers and the client that calls them.

MCP is a standard way to offer "tools" that an application or an AI model can call.

    telegram_server.py   an MCP server with two tools: send_channel_post and check_telegram_settings
    recruitment_server.py  the tools the assistant chatbot chooses from (documents, jobs, post text)
    client.py            starts a server and calls its tools

Two ways the tools are used:
    pages and buttons   the backend code calls one tool by name, after a person clicked
    assistant chat      the AI chooses among the tools (app/graphs/assistant_agent.py); it cannot approve a job
                        or post to Telegram, it can only ask, and a person answers Yes or No
"""
