"""MCP (Model Context Protocol) servers and the client that calls them.

MCP is a standard way to offer "tools" that an application or an AI model can call.

    blogger_server.py    an MCP server with two tools: publish_blog_post and check_blogger_settings
    drive_server.py      an MCP server that only reads Google Drive: the response sheet and the CV files
    recruitment_server.py  the tools the assistant chatbot chooses from (documents, jobs, post text)
    client.py            starts a server and calls its tools

Two ways the tools are used:
    backend code        calls one tool by name: posting after a Yes in the chat, and the Settings checks
    assistant chat      the AI chooses among the tools (app/graphs/assistant_agent.py); it cannot approve a job
                        or post it, it can only ask, and a person answers Yes or No
"""
