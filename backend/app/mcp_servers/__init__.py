"""MCP (Model Context Protocol) servers and the client that calls them.

MCP is a standard way to offer "tools" that an application or an AI model can call.

    blogger_server.py    an MCP server with two tools: publish_blog_post and check_blogger_settings
    recruitment_server.py  the tools the assistant chatbot chooses from (documents, jobs, post text)
    client.py            the list of servers (mcp_servers) and call_tool, which calls one tool
    serve.py             runs a server over stdio, or over HTTP in Docker

Two ways the tools are used:
    backend code        calls one tool by name: posting after a Yes in the chat, and the Settings checks
    assistant chat      the AI chooses among the tools (app/graphs/assistant_agent.py); it cannot approve a job
                        or post it, it can only ask, and a person answers Yes or No
"""
