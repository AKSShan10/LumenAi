"""Google Forms and Google Drive: the only code that talks to Google here. It only reads; it never changes or
deletes anything.

    file_id_from()           the file id inside a Google link
    read_form_rows()         the answers of the job's Google Form, as rows (titles first), from a given answer on
    download_file()          one file as bytes (the uploaded CV)
    check_drive()            the "Test Google Drive" button

Only application_service.py uses this file.

The form is found from the link candidates open (the "Apply now" link of the job post), so no response sheet
is needed. That public link (forms.gle/... or .../forms/d/e/<public id>/viewform) is not the form's own id,
which the Google Forms API needs: the form is looked up once among the forms shared with the service account
(the form whose public address is that link), and its id is saved on the job.

Access is through a Google "service account": a robot account with its own email address. You share the
job's Google Form (as Editor, so its answers can be read) and the folder with the uploaded CVs with that
address. Its key file is secrets/google-drive.json; it is never committed. In the Google Cloud project,
the Google Drive API and the Google Forms API must be enabled.

DRIVE_PROVIDER=fake reads a folder on this computer instead (responses.csv plus the CV files in it),
for tests and for trying the feature without a Google account.
"""
import csv
import io
import logging
import os
import re
from pathlib import Path

from app.core import config

DRIVE_API = "https://www.googleapis.com/drive/v3"
FORMS_API = "https://forms.googleapis.com/v1"
READ_ONLY = ["https://www.googleapis.com/auth/drive.readonly",
             "https://www.googleapis.com/auth/forms.body.readonly",
             "https://www.googleapis.com/auth/forms.responses.readonly"]
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_FORM = "application/vnd.google-apps.form"
BACKEND_DIR = Path(__file__).resolve().parents[4]

log = logging.getLogger("drive")


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


def _google_reason(response) -> str:
    """Google's own sentence about the error, for example "Google Forms API has not been used in project ...". """
    try:
        return str(response.json().get("error", {}).get("message", ""))[:400]
    except Exception:
        return ""


def _get(session, url: str, params: dict):
    try:
        response = session.get(url, params=params, timeout=60)
    except Exception as exc:
        raise DriveError(f"Google Drive could not be reached ({type(exc).__name__})")
    if response.status_code != 200:
        reason = _google_reason(response)
        log.warning("google error %s on %s: %s", response.status_code, url.split("?")[0], reason)
        if reason:
            reason = f" (Google says: {reason})"
    if response.status_code == 404:
        raise DriveError("the file was not found. Share the job's Google Form and its CV folder with the service "
                         "account's email address" + reason)
    if response.status_code == 403:
        raise DriveError("Google refused access. Enable the Google Drive API and the Google Forms API in the Google "
                         "Cloud project, and share the job's Google Form (as Editor) and its CV folder with the "
                         "service account's email address" + reason)
    if response.status_code != 200:
        raise DriveError(f"Google Drive answered with error {response.status_code}" + reason)
    return response


def form_link_ids(link: str) -> tuple[str, str]:
    """(form id, public id) from a Google Forms link; one of them is "".
    .../forms/d/<form id>/edit        -> the form's own id (an editor's link)
    .../forms/d/e/<public id>/viewform -> the public id (the link candidates open)"""
    public = re.search(r"/forms/d/e/([A-Za-z0-9_-]+)", link)
    if public:
        return "", public.group(1)
    own = re.search(r"/forms/d/([A-Za-z0-9_-]+)", link)
    return (own.group(1), "") if own else ("", "")


def _full_link(link: str) -> str:
    """A short forms.gle link leads to the real form address; follow it (no login needed)."""
    if "forms.gle/" not in link:
        return link
    import httpx
    try:
        return str(httpx.get(link, follow_redirects=True, timeout=30).url)
    except Exception as exc:
        raise DriveError(f"the short form link could not be opened ({type(exc).__name__})")


def _find_form_id(session, public_id: str) -> str:
    """The form whose public address has this id, among the forms shared with the service account.
    A form the service account may see in Drive but not open with the Forms API (not an Editor of it) is skipped."""
    page, skipped = "", 0
    while True:
        params = {"q": f"mimeType='{GOOGLE_FORM}' and trashed=false", "fields": "nextPageToken, files(id)",
                  "pageSize": 100, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if page:
            params["pageToken"] = page
        listing = _get(session, f"{DRIVE_API}/files", params).json()
        for file in listing.get("files", []):
            try:
                form = _get(session, f"{FORMS_API}/forms/{file['id']}", {"fields": "responderUri"}).json()
            except DriveError:
                skipped += 1                          # seen in Drive, but the Forms API does not let us open it
                continue
            if public_id in str(form.get("responderUri", "")):
                return file["id"]
        page = listing.get("nextPageToken", "")
        if not page:
            break
    more = f" ({skipped} form(s) in Drive could not be opened: the service account is not their Editor)" if skipped else ""
    raise DriveError("the Google Form of this link was not found. Open the form, click the three dots, "
                     "Add collaborators, and add the service account's email address as Editor" + more)


def _answer_text(answer: dict) -> str:
    """One answer as text: typed answers joined by ", "; an uploaded file becomes its Drive id."""
    texts = [str(part.get("value", "")) for part in answer.get("textAnswers", {}).get("answers", [])]
    files = [str(part.get("fileId", "")) for part in answer.get("fileUploadAnswers", {}).get("answers", [])]
    return ", ".join(value for value in texts + files if value)


def _google_form_rows(form_link: str, from_row: int, form_id: str) -> tuple[list[str], list[list[str]], str]:
    """The form's answers as rows, like a response sheet: titles first ("Timestamp" and the question titles),
    then one row per answer, oldest first (answer 1 = row 2). The Forms API sends every answer; only the rows
    from `from_row` on are returned."""
    session = _session()
    if not form_id:
        form_id, public_id = form_link_ids(_full_link(form_link))
        if not form_id and not public_id:
            raise DriveError("this is not a link to a Google Form")
        form_id = form_id or _find_form_id(session, public_id)
    form = _get(session, f"{FORMS_API}/forms/{form_id}", {}).json()
    questions = [(item["questionItem"]["question"]["questionId"], str(item.get("title", "")))
                 for item in form.get("items", []) if "questionItem" in item]
    answers, page = [], ""
    while True:
        listing = _get(session, f"{FORMS_API}/forms/{form_id}/responses",
                       {"pageSize": 5000, **({"pageToken": page} if page else {})}).json()
        answers += listing.get("responses", [])
        page = listing.get("nextPageToken", "")
        if not page:
            break
    answers.sort(key=lambda answer: str(answer.get("createTime", "")))    # oldest first: new answers come last
    header = ["Timestamp"] + [title for _, title in questions]
    rows = [[str(answer.get("lastSubmittedTime") or answer.get("createTime", ""))]
            + [_answer_text(answer.get("answers", {}).get(question_id, {})) for question_id, _ in questions]
            for answer in answers]
    return header, rows[from_row - 2:], form_id


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


def _fake_form_rows(from_row: int) -> tuple[list[str], list[list[str]]]:
    sheet = _fake_folder() / "responses.csv"
    if not sheet.exists():
        raise DriveError("responses.csv was not found in the fake Drive folder")
    rows = list(csv.reader(io.StringIO(sheet.read_text(encoding="utf-8-sig"))))
    return (rows[0] if rows else []), rows[from_row - 1:]            # row 1 is rows[0]


def _fake_download(file_id: str) -> tuple[str, bytes]:
    name = os.path.basename(file_id)                 # a file id is a file name here; never leave the folder
    path = _fake_folder() / name
    if not path.is_file():
        raise DriveError("the file was not found")
    return name, path.read_bytes()


# ---------------------------------------------------------------- what application_service.py calls

def read_form_rows(form_link: str, from_row: int = 2, form_id: str = "") -> tuple[list[str], list[list[str]], str]:
    """(titles, the answers from answer row `from_row` on, the form's id). Row 1 holds the titles, so the first
    answer is row 2; the checkpoint of a job says where to start. form_id = the id found last time ("" = find it)."""
    if config.DRIVE_PROVIDER == "fake":
        header, rows = _fake_form_rows(from_row)
        return header, rows, form_id or "fake-form"
    return _google_form_rows(form_link, from_row, form_id)


def download_file(file_id: str) -> tuple[str, bytes]:
    """(file name, file content) of one file."""
    return _fake_download(file_id) if config.DRIVE_PROVIDER == "fake" else _google_download(file_id)


def check_drive() -> dict:
    if config.DRIVE_PROVIDER == "fake":
        return {"ok": True, "message": "Fake Google Drive is on (DRIVE_PROVIDER=fake): a folder on this computer is read instead."}
    try:
        credentials = _credentials()
        _get(_session(), f"{DRIVE_API}/files", {"pageSize": 1, "fields": "files(id)"})
        return {"ok": True, "message": "Google Drive answered. Share each job's Google Form (as Editor) and its CV "
                                       f"folder with {credentials.service_account_email}."}
    except DriveError as problem:
        return {"ok": False, "message": f"Not working: {problem}"}
