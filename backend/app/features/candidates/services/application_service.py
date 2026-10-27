"""Applications from the Google Form of one job.

    read_applications()     turns the form's answers (as rows) into applications (name, email, phone, CV file)
    check_applications()    how many answers after the checkpoint are new. Downloads nothing
    fetch_applications()    downloads each new CV, saves the file and one candidate per form answer
    reset_checkpoint()      "Check every answer again": the next check starts at the first answer
    drive_check()           is the Google access set up? (used by the Settings page)

Which form: the "Apply now" link of the job's post (job_posting.apply_url), given when the job is posted in the
Assistant chat. No response sheet and no extra link are needed. The answers are read with the Google Forms API
(drive_service.read_form_rows) and come as rows, oldest first: row 1 holds the titles (Timestamp and the
question titles), answer 1 is row 2.

The checkpoint: job.form_checkpoint_row is the last answer row that is finished. A check or a fetch only looks at
the answers AFTER it. The checkpoint moves forward over every answer that is done (fetched, or empty). If answers
were deleted in the form, use "Check every answer again".

F7 identity check: when the form has a photo question, the photo of each answer is downloaded too (the job posting
tells candidates what it is used for). The face vector is worked out at once (face_service); the photo is never
shown to the candidate and is deleted with the candidate.

How a person stays with their own CV: Google keeps one form answer together: the name, the email, the phone
number and the uploaded CV (its Google Drive id). We take all of them from the same answer and download exactly
that file (by its Drive id). A file name is never used to decide whose CV it is.

The backend code reads Google directly (drive_service.py), after the interviewer clicked a button or the page's
timer asked. No MCP server and no AI are involved in this part.
"""
import logging
import re
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.candidates.schemas import CheckOut, FetchOut
from app.features.candidates.services.cv_storage_service import next_number, save_cv_file, save_photo_file
from app.features.candidates.services import drive_service
from app.features.candidates.services.drive_service import DriveError, file_id_from
from app.features.jobs.models import Job, JobPosting
from app.features.candidates.services.cv_reading_service import read_cv

log = logging.getLogger("applications")

MAX_PER_CLICK = 10               # CVs downloaded in one click; click again for the rest

# Words that show which question holds what (the question titles of the form)
NAME_WORDS = ("name",)
EMAIL_WORDS = ("email", "e-mail")
PHONE_WORDS = ("phone", "mobile", "contact")
CV_WORDS = ("cv", "resume", "résumé", "curriculum", "upload", "file")
# F7: the photo for the identity check (singular or plural, e.g. "Pictures")
PHOTO_WORDS = ("photo", "photos", "picture", "pictures", "selfie", "selfies", "headshot", "headshots")


@dataclass
class Application:
    """One answer of the form."""
    row: int                     # answer row (2 = the first answer), for the checkpoint
    name: str
    email: str
    phone: str
    submitted: str
    file_id: str                 # "" if the row has no usable CV link
    warnings: list = field(default_factory=list)
    photo_id: str = ""           # F7: the Drive id of the photo ("" if none)
    has_photo_question: bool = False

    # Gives a unique key for this form answer (the CV's Drive id) so it is never saved twice
    @property
    def key(self) -> str:
        # Normally the CV's Drive id. A row without a file still needs a key so it is not added twice.
        """A unique key for this form answer (the CV's Drive id), so it is never saved twice."""
        return self.file_id or f"row:{self.submitted}:{self.email or self.name}"


class FormProblem(Exception):
    """The form's answers cannot be used; the message says what to change."""


def _column(headers: list[str], words: tuple) -> int:
    """The first column whose header has one of the words as a whole word. -1 if there is none."""
    for index, header in enumerate(headers):
        if any(re.search(rf"(?<![a-zé]){re.escape(word)}(?![a-zé])", header.lower()) for word in words):
            return index
    return -1


def read_applications(rows: list[list[str]], first_row: int = 2) -> list[Application]:
    """rows[0] holds the titles; the other rows are form answers, the first of them is answer row `first_row`."""
    if not rows or not any(str(cell).strip() for cell in rows[0]):
        raise FormProblem("The form has no questions.")
    headers = [str(cell).strip() for cell in rows[0]]
    name_col, email_col = _column(headers, NAME_WORDS), _column(headers, EMAIL_WORDS)
    photo_col = _column(headers, PHOTO_WORDS)
    # the photo question ("Upload a photo") also says "upload": it must never be taken for the CV question
    phone_col, cv_col = _column(headers, PHONE_WORDS), _column([h if i != photo_col else ""
                                                                for i, h in enumerate(headers)], CV_WORDS)
    if name_col < 0 or cv_col < 0:
        raise FormProblem("The form needs one question with \"name\" in its title and one with \"CV\" in its title. "
                           f"Its questions are: {', '.join(h for h in headers[1:] if h) or 'none'}.")

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
        if photo_col >= 0:                            # F7: the photo for the identity check
            application.has_photo_question = True
            photos = [file_id_from(link) for link in re.split(r"[,\s]+", cell(photo_col)) if link]
            application.photo_id = next((photo for photo in photos if photo), "")
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


def form_link(session: Session, job: Job) -> str:
    """The job's Google Form: the "Apply now" link of its newest successful post (else of its newest post)."""
    posts = session.exec(select(JobPosting).where(JobPosting.job_id == job.id).order_by(JobPosting.id.desc())).all()
    posted = [post for post in posts if post.status == "posted"]
    return ((posted or posts)[0].apply_url if posts else "").strip()


def _new_after_checkpoint(session: Session, job: Job) -> tuple[list[Application], int, str, bool]:
    """Reads only the answers after the job's checkpoint.
    Returns (new applications, last row read, problem, does the form have a photo question)."""
    link = form_link(session, job)
    if not link:
        return [], 0, ("Post this job first, with its Google Form link (in the Assistant chat). "
                       "The applications are read from that form."), False
    if link != job.google_form_link:                  # a new form: find its id again and start at its first answer
        job.google_form_link, job.google_form_id, job.form_checkpoint_row = link, "", 1
    first_row = job.form_checkpoint_row + 1
    try:
        # → drive_service.read_form_rows: reads the Google Form answers
        header, rows, job.google_form_id = drive_service.read_form_rows(link, first_row, job.google_form_id)
        applications = read_applications([header] + rows, first_row)
    except DriveError as problem:
        return [], 0, f"The answers of the Google Form could not be read: {problem}", False
    except FormProblem as problem:
        return [], 0, str(problem), False
    finally:
        session.add(job)                              # keeps the form's id, so it is not looked up again
        session.commit()
    # An answer that is already saved is skipped by its key, so nobody is added twice, whatever the checkpoint says.
    saved_keys = set(session.exec(select(Candidate.source_key).where(Candidate.job_id == job.id)).all())
    new = [application for application in applications if application.key not in saved_keys]
    return new, job.form_checkpoint_row + len(rows), "", _column(header, PHOTO_WORDS) >= 0


def _move_checkpoint(session: Session, job: Job, still_new: list[Application], last_row_read: int) -> None:
    """Every row before the first answer that still waits is finished. With nothing waiting, all rows read are finished."""
    checkpoint = still_new[0].row - 1 if still_new else last_row_read
    if checkpoint > job.form_checkpoint_row:
        job.form_checkpoint_row = checkpoint
        session.add(job)
        session.commit()


def check_applications(session: Session, job: Job) -> CheckOut:
    """Counts the form answers after the checkpoint that are not fetched yet. No CV is downloaded."""
    new, last_row_read, problem, _ = _new_after_checkpoint(session, job)
    if problem:
        return CheckOut(ok=False, message=problem, checkpoint_row=job.form_checkpoint_row, form_link=form_link(session, job))
    rows_read = last_row_read - job.form_checkpoint_row
    _move_checkpoint(session, job, new, last_row_read)
    if new:
        message = f"{len(new)} new application(s) in the form. Click Fetch new applications to download the CV(s)."
    else:
        message = "No new applications since the checkpoint."
    return CheckOut(ok=True, message=message, new=len(new), rows_read=rows_read, checkpoint_row=job.form_checkpoint_row,
                    form_link=job.google_form_link)


def reset_checkpoint(session: Session, job: Job) -> CheckOut:
    """Starts again at the first answer of the form, then checks. Nobody is added twice: saved answers are skipped."""
    job.form_checkpoint_row = 1
    session.add(job)
    session.commit()
    return check_applications(session, job)


# Downloads the CVs of new form answers, saves one candidate each, then calls start_screening
def fetch_applications(session: Session, job: Job) -> FetchOut:
    # 1. only the answers after the checkpoint, and of those only the ones that are not saved yet
    """Downloads the CVs (and photos) of new form answers, saves one candidate each, starts the screening."""
    new, last_row_read, problem, photo_question = _new_after_checkpoint(session, job)
    if problem:
        return FetchOut(ok=False, message=problem)
    now, later = new[:MAX_PER_CLICK], new[MAX_PER_CLICK:]

    # 2. one candidate per form answer: the name, the email, the phone and the CV of the SAME answer.
    #    The CV is downloaded by the Drive id in that answer, so it is exactly that person's file.
    emails = {email.lower() for email in session.exec(select(Candidate.email).where(Candidate.job_id == job.id)).all() if email}
    needs_review = 0
    for application in now:
        file_name, data, warnings = "", b"", list(application.warnings)
        reading = None
        if application.file_id:
            try:
                # → drive_service.download_file: downloads this answer's CV from Google Drive
                file_name, data = drive_service.download_file(application.file_id)
            except (DriveError, OSError) as problem:
                warnings.append(f"The CV could not be downloaded: {problem}")
            if data:
                reading = read_cv(file_name, data)    # plain code; the AI reads a scanned PDF later, in the screening
                if reading.problem:
                    warnings.append(reading.problem)
        cv_text = reading.text if reading else ""
        if cv_text and not _name_is_in(application.name, cv_text):
            warnings.append("The name from the form was not found in the CV. Please check that it is the right file")
        if application.email and application.email.lower() in emails:
            warnings.append("This email address applied more than once")
        emails.add(application.email.lower())

        photo_name, photo_data, face_status = "", b"", ""
        if application.has_photo_question:            # F7: the photo for the identity check
            face_status = "" if application.photo_id else "no_photo"
            if not face_status:
                try:
                    # → drive_service.download_file: downloads this answer's photo from Google Drive
                    photo_name, photo_data = drive_service.download_file(application.photo_id)
                except (DriveError, OSError) as problem:
                    face_status = "download_failed"
                    warnings.append(f"The photo could not be downloaded: {problem}")

        candidate = Candidate(job_id=job.id, number=next_number(session, job.id), full_name=application.name, email=application.email,
                              phone=application.phone, applied_at=application.submitted, source="google_form",
                              source_key=application.key, drive_file_id=application.file_id,
                              original_file_name=file_name[:200], cv_text=cv_text,
                              text_source=reading.source if reading else "", read_problem=reading.problem if reading else "",
                              status="new" if cv_text and not (reading and reading.problem) else "needs_review",
                              warnings=warnings)
        session.add(candidate)
        session.flush()                               # saves the row now, so the next candidate gets the next number
        if data:
            candidate.file_path = save_cv_file(candidate, file_name, data)
        candidate.face_status = face_status
        if photo_data:
            candidate.photo_path = save_photo_file(candidate, photo_name, photo_data)
            from app.features.identity.services.identity_service import read_photo_face
            read_photo_face(candidate)                # the face vector (or why the photo cannot be used)
        needs_review += candidate.status == "needs_review"
    session.commit()
    _move_checkpoint(session, job, later, last_row_read)          # 3. the fetched answers are finished
    if now:
        from app.features.screening.services.screening_worker import start_screening
        start_screening(job.id)                       # 4. the backend screens the new CVs by itself, in the background
    log.info("applications job=%s added=%d needs_review=%d left=%d checkpoint_row=%d", job.id, len(now), needs_review,
             len(later), job.form_checkpoint_row)

    # F7: photos of answers saved before the form had its photo question (only read when the form has one)
    photos = _fill_missing_photos(session, job) if photo_question else 0
    if not now:
        message = "No new applications since the checkpoint."
    else:
        message = f"{len(now)} new application(s) fetched and saved."
        if needs_review:
            message += f" {needs_review} need(s) a look."
        if later:
            message += f" {len(later)} more are waiting: click Fetch new applications again."
    if photos:
        message += f" {photos} photo(s) of earlier applications were added."
    return FetchOut(ok=True, message=message, added=len(now), needs_review=needs_review, left_for_next_time=len(later))


def _fill_missing_photos(session: Session, job: Job) -> int:
    """F7: candidates saved before the form had a photo question (face_status "") get their photo now, once.
    Reads every answer of the form, matches each saved candidate by its own answer (source_key, never by name) and
    downloads that answer's photo. Returns how many photos were added."""
    waiting = session.exec(select(Candidate).where(Candidate.job_id == job.id, Candidate.source == "google_form",
                                                   Candidate.photo_path == "", Candidate.face_status == "")).all()
    link = form_link(session, job)
    if not waiting or not link:
        return 0
    try:
        # → drive_service.read_form_rows: every answer of the form, from the first one
        header, rows, job.google_form_id = drive_service.read_form_rows(link, 2, job.google_form_id)
        by_key = {application.key: application for application in read_applications([header] + rows, 2)}
    except (DriveError, FormProblem):
        return 0                                      # tried again at the next fetch
    from app.features.identity.services.identity_service import read_photo_face
    added = 0
    for candidate in waiting:
        application = by_key.get(candidate.source_key)   # the candidate's OWN form answer (by its key, never by name)
        if not application or not application.photo_id:
            candidate.face_status = "no_photo"        # not asked again at every fetch
            continue
        try:
            # → drive_service.download_file: this answer's photo from Google Drive
            photo_name, photo_data = drive_service.download_file(application.photo_id)
        except (DriveError, OSError):
            candidate.face_status = "download_failed"
            continue
        candidate.photo_path = save_photo_file(candidate, photo_name, photo_data)
        read_photo_face(candidate)                    # the face vector (or why the photo cannot be used)
        added += 1
    session.add(job)
    session.add_all(waiting)
    session.commit()
    log.info("photos added job=%s added=%d", job.id, added)
    return added


# Passes the Settings page "Test Google Drive" check on to drive_service.check_drive
def drive_check() -> dict:
    """The Settings page "Test Google Drive" check (drive_service.check_drive)."""
    return drive_service.check_drive()
