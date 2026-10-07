"""Applications from the Google Form of one job.

    read_applications()     turns the rows of the response sheet into applications (name, email, phone, CV link)
    check_applications()    how many answers are in the sheet, and how many are new. Downloads nothing
    fetch_applications()    downloads each new CV, saves the file and one candidate per form answer
    drive_check()           is the Google Drive access set up? (used by the Settings page)

How a person stays with their own CV: Google writes one form answer as ONE ROW of the response sheet, and
that row holds the name, the email, the phone number and the link to the uploaded CV. We take all of them
from the same row and download exactly the file that link points to (by its Google Drive id). A file name is
never used to decide whose CV it is.

The backend code reads Google Drive directly (drive_service.py), after the interviewer clicked a button or
the page's timer asked. No MCP server and no AI are involved in this part.
"""
import logging
import re
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.candidates.schemas import CheckOut, FetchOut
from app.features.candidates.services.cv_storage_service import save_cv_file
from app.features.candidates.services import drive_service
from app.features.candidates.services.drive_service import DriveError, file_id_from
from app.features.jobs.models import Job
from app.utils.file_text_utils import text_from_file

log = logging.getLogger("applications")

MAX_PER_CLICK = 10               # CVs downloaded in one click; click again for the rest

# Words that show which column of the sheet holds what (Google uses your question titles as headers)
NAME_WORDS = ("name",)
EMAIL_WORDS = ("email", "e-mail")
PHONE_WORDS = ("phone", "mobile", "contact")
CV_WORDS = ("cv", "resume", "résumé", "curriculum", "upload", "file")


@dataclass
class Application:
    """One row of the response sheet."""
    row: int                     # row number in the sheet (2 = the first answer), for messages
    name: str
    email: str
    phone: str
    submitted: str
    file_id: str                 # "" if the row has no usable CV link
    warnings: list = field(default_factory=list)

    @property
    def key(self) -> str:
        # Normally the CV's Drive id. A row without a file still needs a key so it is not added twice.
        return self.file_id or f"row:{self.submitted}:{self.email or self.name}"


class SheetProblem(Exception):
    """The sheet cannot be used; the message says what to change."""


def _column(headers: list[str], words: tuple) -> int:
    """The first column whose header has one of the words as a whole word. -1 if there is none."""
    for index, header in enumerate(headers):
        if any(re.search(rf"(?<![a-zé]){re.escape(word)}(?![a-zé])", header.lower()) for word in words):
            return index
    return -1


def read_applications(rows: list[list[str]]) -> list[Application]:
    if not rows:
        raise SheetProblem("The sheet is empty. Paste the link of the form's response sheet.")
    headers = [str(cell).strip() for cell in rows[0]]
    name_col, email_col = _column(headers, NAME_WORDS), _column(headers, EMAIL_WORDS)
    phone_col, cv_col = _column(headers, PHONE_WORDS), _column(headers, CV_WORDS)
    if name_col < 0 or cv_col < 0:
        raise SheetProblem("The sheet needs one column with \"name\" in its title and one with \"CV\" in its title. "
                           f"Its columns are: {', '.join(h for h in headers if h) or 'none'}.")

    applications = []
    for number, cells in enumerate(rows[1:], start=2):
        cell = lambda index: str(cells[index]).strip() if 0 <= index < len(cells) else ""   # noqa: E731
        name, email, links = cell(name_col), cell(email_col), cell(cv_col)
        if not (name or email or links):
            continue                                  # an empty row
        application = Application(row=number, name=name, email=email, phone=cell(phone_col),
                                  submitted=cell(0), file_id="")
        file_ids = [file_id_from(link) for link in re.split(r"[,\s]+", links) if link]
        file_ids = [file_id for file_id in file_ids if file_id]
        if file_ids:
            application.file_id = file_ids[0]
        else:
            application.warnings.append("No CV file was attached to this form answer")
        if len(file_ids) > 1:
            application.warnings.append(f"{len(file_ids)} files were uploaded; only the first one was fetched")
        if not name:
            application.warnings.append("No name was given in this form answer")
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            application.warnings.append("The email address does not look right")
        applications.append(application)
    return applications


def _name_is_in(name: str, cv_text: str) -> bool:
    """Does at least one word of the name appear in the CV? (A check for a person, not a proof.)"""
    words = [word for word in re.findall(r"[^\W\d_]{3,}", name.lower())]
    text = cv_text.lower()
    return not words or any(word in text for word in words)


def _sheet_applications(job: Job) -> tuple[list[Application], str]:
    """Reads the response sheet of the job from Google Drive. Returns (applications, problem)."""
    if not job.response_sheet_url:
        return [], "Save the link of the response sheet for this job first."
    try:
        rows = drive_service.read_response_sheet(job.response_sheet_url)
        return read_applications(rows), ""
    except DriveError as problem:
        return [], f"The response sheet could not be read: {problem}"
    except SheetProblem as problem:
        return [], str(problem)


def _new_only(session: Session, job: Job, applications: list[Application]) -> list[Application]:
    saved_keys = set(session.exec(select(Candidate.source_key).where(Candidate.job_id == job.id)).all())
    return [application for application in applications if application.key not in saved_keys]


def check_applications(session: Session, job: Job) -> CheckOut:
    """Counts the form answers that are not fetched yet. Reads the sheet only; no CV is downloaded."""
    applications, problem = _sheet_applications(job)
    if problem:
        return CheckOut(ok=False, message=problem)
    new = len(_new_only(session, job, applications))
    if not applications:
        message = "The sheet has no form answers yet."
    elif new == 0:
        message = "No new applications. Everything in the sheet was fetched before."
    else:
        message = f"{new} new application(s) in the sheet. Click Fetch new applications to download the CV(s)."
    return CheckOut(ok=True, message=message, in_sheet=len(applications), new=new,
                    already_fetched=len(applications) - new)


def fetch_applications(session: Session, job: Job) -> FetchOut:
    # 1. the rows of the response sheet, and of those only the answers that are not saved yet
    applications, problem = _sheet_applications(job)
    if problem:
        return FetchOut(ok=False, message=problem)
    new = _new_only(session, job, applications)
    now, later = new[:MAX_PER_CLICK], new[MAX_PER_CLICK:]

    # 2. one candidate per form answer: the name, the email, the phone and the CV of the SAME row.
    #    The CV is downloaded by the Drive id in that row, so it is exactly that person's file.
    emails = {email.lower() for email in session.exec(select(Candidate.email).where(Candidate.job_id == job.id)).all() if email}
    needs_review = 0
    for application in now:
        file_name, data, cv_text, warnings = "", b"", "", list(application.warnings)
        if application.file_id:
            try:
                file_name, data = drive_service.download_file(application.file_id)
            except (DriveError, OSError) as problem:
                warnings.append(f"The CV could not be downloaded: {problem}")
            if data:
                try:
                    cv_text = text_from_file(file_name, data)
                except ValueError as problem:
                    warnings.append("The CV was saved, but its text could not be read: " + str(problem))
        if cv_text and not _name_is_in(application.name, cv_text):
            warnings.append("The name from the form was not found in the CV. Please check that it is the right file")
        if application.email and application.email.lower() in emails:
            warnings.append("This email address applied more than once")
        emails.add(application.email.lower())

        candidate = Candidate(job_id=job.id, full_name=application.name, email=application.email,
                              phone=application.phone, applied_at=application.submitted, source="google_form",
                              source_key=application.key, drive_file_id=application.file_id,
                              original_file_name=file_name[:200], cv_text=cv_text,
                              status="new" if cv_text else "needs_review", warnings=warnings)
        session.add(candidate)
        session.flush()                               # gives the candidate its number, needed for the file name
        if data:
            candidate.file_path = save_cv_file(candidate, file_name, data)
        needs_review += candidate.status == "needs_review"
    session.commit()
    log.info("applications job=%s added=%d needs_review=%d left=%d", job.id, len(now), needs_review, len(later))

    if not applications:
        message = "The sheet has no form answers yet."
    elif not now:
        message = "No new applications. Everything in the sheet was fetched before."
    else:
        message = f"{len(now)} new application(s) fetched and saved."
        if needs_review:
            message += f" {needs_review} need(s) a look."
        if later:
            message += f" {len(later)} more are waiting: click Fetch new applications again."
    return FetchOut(ok=True, message=message, added=len(now), needs_review=needs_review, left_for_next_time=len(later))


def drive_check() -> dict:
    return drive_service.check_drive()
