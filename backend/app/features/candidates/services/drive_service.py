"""Google Drive: the only code that talks to Google Drive. It only reads; it never changes or deletes anything.

    file_id_from()           the file id inside a Google link
    read_response_sheet()    the rows of the form's response sheet
    download_file()          one file as bytes
    check_drive()            the "Test Google Drive" button

Only application_service.py uses this file.

Access is through a Google "service account": a robot account with its own email address. You share the
job's folder (form, response sheet, CV folder) with that address as Viewer. Its key file is
secrets/google-drive.json; it is never committed.

DRIVE_PROVIDER=fake reads a folder on this computer instead (responses.csv plus the CV files in it),
for tests and for trying the feature without a Google account.
"""
import csv
import io
import os
import re
from pathlib import Path

from app.core import config

DRIVE_API = "https://www.googleapis.com/drive/v3"
READ_ONLY = ["https://www.googleapis.com/auth/drive.readonly"]
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
BACKEND_DIR = Path(__file__).resolve().parents[4]


class DriveError(Exception):
    """A problem the interviewer can fix; the message is in plain words."""


def file_id_from(link: str) -> str:
    """Accepts a Google link (.../d/<id>/..., ...?id=<id>) or the id itself. Returns "" if there is none."""
    link = link.strip()
    found = re.search(r"/d/([A-Za-z0-9_-]+)", link) or re.search(r"[?&]id=([^&\s,]+)", link)
    if found:
        return found.group(1)
    return "" if "/" in link or " " in link else link


def _path(setting: str) -> Path:
    """A path from .env: as given, inside backend/, or next to backend/ (the project folder)."""
    path = Path(setting)
    for candidate in (path, BACKEND_DIR / path, BACKEND_DIR.parent / path):
        if candidate.exists():
            return candidate
    return BACKEND_DIR.parent / path


# ---------------------------------------------------------------- Google

def _credentials():
    from google.oauth2 import service_account
    path = _path(config.GOOGLE_DRIVE_KEY_FILE)
    if not path.exists():
        raise DriveError(f"the Google Drive key file was not found ({config.GOOGLE_DRIVE_KEY_FILE})")
    try:
        return service_account.Credentials.from_service_account_file(str(path), scopes=READ_ONLY)
    except Exception:
        raise DriveError("the Google Drive key file is not a valid service-account key")


def _session():
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(_credentials())


def _get(session, url: str, params: dict):
    try:
        response = session.get(url, params=params, timeout=60)
    except Exception as exc:
        raise DriveError(f"Google Drive could not be reached ({type(exc).__name__})")
    if response.status_code == 404:
        raise DriveError("the file was not found. Share the job's folder with the service account's email address")
    if response.status_code == 403:
        raise DriveError("Google refused access. Enable the Google Drive API in the Google Cloud project, "
                         "and share the job's folder with the service account's email address")
    if response.status_code != 200:
        raise DriveError(f"Google Drive answered with error {response.status_code}")
    return response


def _google_sheet_rows(sheet: str) -> list[list[str]]:
    sheet_id = file_id_from(sheet)
    if not sheet_id:
        raise DriveError("this is not a link to a Google Sheet")
    session = _session()
    info = _get(session, f"{DRIVE_API}/files/{sheet_id}", {"fields": "mimeType", "supportsAllDrives": "true"}).json()
    if info.get("mimeType") != GOOGLE_SHEET:
        raise DriveError("the link does not open a Google Sheet. Paste the link of the form's response sheet")
    # Google gives the first tab of the sheet as CSV text; that tab holds the form answers.
    text = _get(session, f"{DRIVE_API}/files/{sheet_id}/export", {"mimeType": "text/csv"}).content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _google_download(file_id: str) -> tuple[str, bytes]:
    session = _session()
    info = _get(session, f"{DRIVE_API}/files/{file_id}", {"fields": "name, mimeType", "supportsAllDrives": "true"}).json()
    if info.get("mimeType") == GOOGLE_DOC:           # a Google Doc has no file of its own: export it as PDF
        content = _get(session, f"{DRIVE_API}/files/{file_id}/export", {"mimeType": "application/pdf"}).content
        return info["name"] + ".pdf", content
    return info["name"], _get(session, f"{DRIVE_API}/files/{file_id}", {"alt": "media", "supportsAllDrives": "true"}).content


# ---------------------------------------------------------------- fake (a folder on this computer)

def _fake_folder() -> Path:
    folder = _path(config.DRIVE_FAKE_FOLDER)
    if not folder.is_dir():
        raise DriveError(f"the folder {config.DRIVE_FAKE_FOLDER} was not found on this computer (DRIVE_PROVIDER=fake)")
    return folder


def _fake_sheet_rows() -> list[list[str]]:
    sheet = _fake_folder() / "responses.csv"
    if not sheet.exists():
        raise DriveError("responses.csv was not found in the fake Drive folder")
    return list(csv.reader(io.StringIO(sheet.read_text(encoding="utf-8-sig"))))


def _fake_download(file_id: str) -> tuple[str, bytes]:
    name = os.path.basename(file_id)                 # a file id is a file name here; never leave the folder
    path = _fake_folder() / name
    if not path.is_file():
        raise DriveError("the file was not found")
    return name, path.read_bytes()


# ---------------------------------------------------------------- what application_service.py calls

def read_response_sheet(sheet: str) -> list[list[str]]:
    """All rows of the response sheet, the header row first."""
    return _fake_sheet_rows() if config.DRIVE_PROVIDER == "fake" else _google_sheet_rows(sheet)


def download_file(file_id: str) -> tuple[str, bytes]:
    """(file name, file content) of one file."""
    return _fake_download(file_id) if config.DRIVE_PROVIDER == "fake" else _google_download(file_id)


def check_drive() -> dict:
    if config.DRIVE_PROVIDER == "fake":
        return {"ok": True, "message": "Fake Google Drive is on (DRIVE_PROVIDER=fake): a folder on this computer is read instead."}
    try:
        credentials = _credentials()
        _get(_session(), f"{DRIVE_API}/files", {"pageSize": 1, "fields": "files(id)"})
        return {"ok": True, "message": "Google Drive answered. Share each job's folder with "
                                       f"{credentials.service_account_email} as Viewer."}
    except DriveError as problem:
        return {"ok": False, "message": f"Not working: {problem}"}
