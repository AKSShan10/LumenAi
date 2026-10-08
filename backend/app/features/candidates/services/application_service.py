"""Applications from the Google Form of one job.

    read_applications()     turns rows of the response sheet into applications (name, email, phone, CV link)
    check_applications()    how many answers after the checkpoint are new. Downloads nothing
    fetch_applications()    downloads each new CV, saves the file and one candidate per form answer
    reset_checkpoint()      "Check the whole sheet again": the next check starts at the first answer
    drive_check()           is the Google Drive access set up? (used by the Settings page)

The checkpoint: job.sheet_checkpoint_row is the last row of the sheet that is finished. A check or a fetch asks
Google only for the rows AFTER it, so the whole sheet is not read again each time. Row 1 holds the column
titles, so a new job starts with checkpoint 1. The checkpoint moves forward over every row that is done
(fetched, or empty). If rows were sorted or deleted in the sheet, use "Check the whole sheet again".

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
from app.features.candidates.services.cv_storage_service import next_number, save_cv_file
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


def read_applications(rows: list[list[str]], first_row: int = 2) -> list[Application]:
    """rows[0] holds the column titles; the other rows are form answers, the first of them is sheet row `first_row`."""
    if not rows or not any(str(cell).strip() for cell in rows[0]):
        raise SheetProblem("The sheet is empty. Paste the link of the form's response sheet.")
    headers = [str(cell).strip() for cell in rows[0]]
    name_col, email_col = _column(headers, NAME_WORDS), _column(headers, EMAIL_WORDS)
    phone_col, cv_col = _column(headers, PHONE_WORDS), _column(headers, CV_WORDS)
    if name_col < 0 or cv_col < 0:
        raise SheetProblem("The sheet needs one column with \"name\" in its title and one with \"CV\" in its title. "
                           f"Its columns are: {', '.join(h for h in headers if h) or 'none'}.")

    applications = []
    for number, cells in enumerate(rows[1:], start=first_row):
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


def _new_after_checkpoint(session: Session, job: Job) -> tuple[list[Application], int, str]:
    """Reads only the rows after the job's checkpoint. Returns (new applications, last row read, problem)."""
    if not job.response_sheet_url:
        return [], 0, "Save the link of the response sheet for this job first."
    first_row = job.sheet_checkpoint_row + 1
    try:
        header, rows = drive_service.read_sheet_rows(job.response_sheet_url, first_row)
        applications = read_applications([header] + rows, first_row)
    except DriveError as problem:
        return [], 0, f"The response sheet could not be read: {problem}"
    except SheetProblem as problem:
        return [], 0, str(problem)
    # An answer that is already saved is skipped by its key, so nobody is added twice, whatever the checkpoint says.
    saved_keys = set(session.exec(select(Candidate.source_key).where(Candidate.job_id == job.id)).all())
    new = [application for application in applications if application.key not in saved_keys]
    return new, job.sheet_checkpoint_row + len(rows), ""


def _move_checkpoint(session: Session, job: Job, still_new: list[Application], last_row_read: int) -> None:
    """Every row before the first answer that still waits is finished. With nothing waiting, all rows read are finished."""
    checkpoint = still_new[0].row - 1 if still_new else last_row_read
    if checkpoint > job.sheet_checkpoint_row:
        job.sheet_checkpoint_row = checkpoint
        session.add(job)
        session.commit()


def check_applications(session: Session, job: Job) -> CheckOut:
    """Counts the form answers after the checkpoint that are not fetched yet. No CV is downloaded."""
    new, last_row_read, problem = _new_after_checkpoint(session, job)
    if problem:
        return CheckOut(ok=False, message=problem, checkpoint_row=job.sheet_checkpoint_row)
    rows_read = last_row_read - job.sheet_checkpoint_row
    _move_checkpoint(session, job, new, last_row_read)
    if new:
        message = f"{len(new)} new application(s) in the sheet. Click Fetch new applications to download the CV(s)."
    else:
        message = "No new applications since the checkpoint."
    return CheckOut(ok=True, message=message, new=len(new), rows_read=rows_read, checkpoint_row=job.sheet_checkpoint_row)


def reset_checkpoint(session: Session, job: Job) -> CheckOut:
    """Starts again at the first answer of the sheet, then checks. Nobody is added twice: saved answers are skipped."""
    job.sheet_checkpoint_row = 1
    session.add(job)
    session.commit()
    return check_applications(session, job)


def fetch_applications(session: Session, job: Job) -> FetchOut:
    # 1. only the rows after the checkpoint, and of those only the answers that are not saved yet
    new, last_row_read, problem = _new_after_checkpoint(session, job)
    if problem:
        return FetchOut(ok=False, message=problem)
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

        candidate = Candidate(job_id=job.id, number=next_number(session, job.id), full_name=application.name, email=application.email,
                              phone=application.phone, applied_at=application.submitted, source="google_form",
                              source_key=application.key, drive_file_id=application.file_id,
                              original_file_name=file_name[:200], cv_text=cv_text,
                              status="new" if cv_text else "needs_review", warnings=warnings)
        session.add(candidate)
        session.flush()                               # saves the row now, so the next candidate gets the next number
        if data:
            candidate.file_path = save_cv_file(candidate, file_name, data)
        needs_review += candidate.status == "needs_review"
    session.commit()
    _move_checkpoint(session, job, later, last_row_read)          # 3. the fetched rows are finished
    log.info("applications job=%s added=%d needs_review=%d left=%d checkpoint_row=%d", job.id, len(now), needs_review,
             len(later), job.sheet_checkpoint_row)

    if not now:
        message = "No new applications since the checkpoint."
    else:
        message = f"{len(now)} new application(s) fetched and saved."
        if needs_review:
            message += f" {needs_review} need(s) a look."
        if later:
            message += f" {len(later)} more are waiting: click Fetch new applications again."
    return FetchOut(ok=True, message=message, added=len(now), needs_review=needs_review, left_for_next_time=len(later))


def drive_check() -> dict:
    return drive_service.check_drive()
