"""The Google Drive MCP server. It only reads. It offers three tools:

    read_response_sheet(sheet)   the rows of a form's response sheet
    download_file(file_id)       one file, as base64 text
    check_drive_settings()       is the Google Drive access set up?

The backend starts it when the interviewer checks for or fetches applications:   python -m app.mcp_servers.drive_server
It talks over standard input / output (the "stdio" transport).
Every tool answers with JSON. A problem is returned as {"error": "..."} in plain words.
"""
import base64
import json

from mcp.server.fastmcp import FastMCP

from app.features.candidates.services import drive_service
from app.features.candidates.services.drive_service import DriveError

server = FastMCP("lumenai-drive")


@server.tool()
def read_response_sheet(sheet: str) -> str:
    """Read the response sheet of a Google Form (link or id). Returns JSON: {"rows": [[...], ...]}, header row first."""
    try:
        return json.dumps({"rows": drive_service.read_response_sheet(sheet)})
    except DriveError as problem:
        return json.dumps({"error": str(problem)})


@server.tool()
def download_file(file_id: str) -> str:
    """Download one file by its Google Drive id. Returns JSON: {"name": "...", "data_base64": "..."}."""
    try:
        name, data = drive_service.download_file(file_id)
        return json.dumps({"name": name, "data_base64": base64.b64encode(data).decode()})
    except (DriveError, OSError) as problem:
        return json.dumps({"error": str(problem)})


@server.tool()
def check_drive_settings() -> str:
    """Check the Google Drive access without reading any file. Returns JSON: {"ok": true/false, "message": "..."}."""
    return json.dumps(drive_service.check_drive())


if __name__ == "__main__":
    server.run()          # stdio transport
