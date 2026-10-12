"""CV files on this computer, and the candidates that are added by hand.

    next_number()        the next candidate number inside one job (1, 2, 3 ... per job)
    save_cv_file()       writes one CV into the storage folder and returns where it is
    cv_file()            the saved file of one candidate (to open or download it)
    delete_candidate()   removes the candidate and the saved file
    add_uploaded_cv()    manual upload: one file becomes one candidate
    candidate_out()      the list row shown on the Candidates page

Where files go:
    <STORAGE_DIR>/cvs/job_<job id>/google_form/candidate_<number>_<name>.<ext>     fetched from the Google Form
    <STORAGE_DIR>/cvs/job_<job id>/uploaded/candidate_<number>_<name>.<ext>        uploaded by hand

What keeps two CVs apart is the candidate's NUMBER inside the job (candidate.number). Every job counts on its
own: 1, 2, 3 ... Inside one job no two candidates share a number, and every job has its own folder. So two
people who both send "CV.pdf", or two people with the same name, get two different files. When the last
candidate of a job is deleted, the next new one gets that number again (its old file was deleted with it). The name in the file name is only there so a person can read the folder; the code never
uses it to find a file. The exact place of each file is saved in candidate.file_path.
The storage folder holds real CVs: it is in .gitignore and must never be committed.
"""
import hashlib
import logging
import os
import re
from pathlib import Path

from sqlmodel import Session, func, select

from app.core import config
from app.features.candidates.models import Candidate
from app.features.candidates.schemas import CandidateOut, UploadOut
from app.features.jobs.models import Job
from app.features.candidates.services.cv_reading_service import read_cv

log = logging.getLogger("candidates")

BACKEND_DIR = Path(__file__).resolve().parents[4]
MAX_FILE_BYTES = 5 * 1024 * 1024
ALLOWED = (".pdf", ".docx", ".doc", ".txt")
FOLDERS = {"google_form": "google_form", "upload": "uploaded"}     # one folder per way a CV arrived


def storage_dir() -> Path:
    """STORAGE_DIR from .env; a path that does not start at the disk root is inside backend/."""
    path = Path(config.STORAGE_DIR)
    return path if path.is_absolute() else BACKEND_DIR / path


def _for_file_name(full_name: str) -> str:
    """"Rahim Uddin" -> "rahim-uddin". Only plain letters and digits are kept; anything else may be empty."""
    return re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")[:40]


def next_number(session: Session, job_id: int) -> int:
    """The highest number in this job plus one. Candidates of other jobs are not counted."""
    highest = session.exec(select(func.max(Candidate.number)).where(Candidate.job_id == job_id)).one()
    return (highest or 0) + 1


def save_cv_file(candidate: Candidate, original_name: str, data: bytes) -> str:
    """Writes the file and returns its place inside the storage folder (saved in candidate.file_path)."""
    extension = os.path.splitext(original_name)[1].lower()[:10]
    name = _for_file_name(candidate.full_name)
    file_name = f"candidate_{candidate.number}_{name}{extension}" if name else f"candidate_{candidate.number}{extension}"
    relative = Path("cvs") / f"job_{candidate.job_id}" / FOLDERS.get(candidate.source, "other") / file_name
    target = storage_dir() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative.as_posix()


def cv_file(candidate: Candidate) -> Path | None:
    """The saved CV, or None if there is none (never downloaded, or the file was removed from the disk)."""
    if not candidate.file_path:
        return None
    path = storage_dir() / candidate.file_path
    return path if path.is_file() else None


def delete_candidate(session: Session, candidate: Candidate) -> None:
    path = cv_file(candidate)
    if path:
        path.unlink()                                 # the file in Google Drive is not touched
    forget_screening(session, candidate)
    session.delete(candidate)
    session.commit()


def add_uploaded_cv(session: Session, job: Job, filename: str, data: bytes,
                    full_name: str = "", email: str = "", phone: str = "") -> UploadOut:
    """Manual upload, for a CV the organization received in another way. The name, email and phone are
    whatever the interviewer typed with this file (they may be empty)."""
    if os.path.splitext(filename)[1].lower() not in ALLOWED:
        return UploadOut(ok=False, message=f"{filename}: only PDF, DOCX, DOC and TXT files can be uploaded.")
    if len(data) > MAX_FILE_BYTES:
        return UploadOut(ok=False, message=f"{filename}: the file is larger than 5 MB.")

    key = "upload:" + hashlib.sha256(data).hexdigest()        # the same file twice for one job is skipped
    if session.exec(select(Candidate).where(Candidate.job_id == job.id, Candidate.source_key == key)).first():
        return UploadOut(ok=False, message=f"{filename}: this exact file was already added to this job.")

    reading = read_cv(filename, data)                 # plain code; the AI reads a scanned PDF later, in the screening
    warnings = [reading.problem] if reading.problem else []
    if not full_name.strip():
        warnings.append("No name was given with this file")

    candidate = Candidate(job_id=job.id, number=next_number(session, job.id), full_name=full_name.strip(), email=email.strip(), phone=phone.strip(),
                          source="upload", source_key=key, original_file_name=filename[:200], cv_text=reading.text,
                          text_source=reading.source, read_problem=reading.problem,
                          status="needs_review" if reading.problem else "new", warnings=warnings)
    session.add(candidate)
    session.flush()                                   # gives the row its id
    candidate.file_path = save_cv_file(candidate, filename, data)
    session.commit()
    log.info("cv uploaded job=%s candidate=%s number=%s status=%s", job.id, candidate.id, candidate.number, candidate.status)
    from app.features.screening.services.screening_worker import start_screening
    start_screening(job.id)                           # the backend screens the new CV by itself, in the background
    return UploadOut(ok=True, message=f"{filename} was added.", candidate_id=candidate.id)


def forget_screening(session: Session, candidate: Candidate) -> None:
    """Removes the screening result, the shortlist entry and the interview of a candidate that is deleted."""
    from app.features.screening.models import ScreeningResult, ShortlistEntry   # the screening feature uses the candidates
    for result in session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).all():
        session.delete(result)
    for entry in session.exec(select(ShortlistEntry).where(ShortlistEntry.candidate_id == candidate.id)).all():
        session.delete(entry)
    from app.features.interviews.models import CallMessage, InterviewSession     # and their interview + call chat
    for interview in session.exec(select(InterviewSession).where(InterviewSession.candidate_id == candidate.id)).all():
        for message in session.exec(select(CallMessage).where(CallMessage.session_id == interview.id)).all():
            session.delete(message)
        session.delete(interview)


SCREENING_STATES = {"passed": "included", "excluded": "excluded", "needs_review": "needs_review"}


def candidate_out(row: Candidate, screening=None) -> CandidateOut:
    """screening: the candidate's ScreeningResult, or None (not screened yet)."""
    if screening is None or screening.stale:
        state, reason = "waiting", ""
    else:
        state = screening.decision or SCREENING_STATES.get(screening.result, "needs_review")
        reason = screening.reason
    warnings = list(row.warnings or [])
    text_source = row.text_source
    if screening is not None and not screening.stale and screening.text_source:
        text_source = screening.text_source           # the screening may have read more (a scanned PDF, by the AI)
        if not screening.read_problem and row.read_problem:
            warnings = [w for w in warnings if w != row.read_problem]   # the screening could read it after all
    return CandidateOut(screening_state=state, screening_reason=reason, decided=bool(screening and screening.decision),id=row.id, number=row.number, job_id=row.job_id, full_name=row.full_name, email=row.email, phone=row.phone,
                        applied_at=row.applied_at, source=row.source, original_file_name=row.original_file_name,
                        has_file=cv_file(row) is not None, saved_as=row.file_path, cv_words=len(row.cv_text.split()), text_source=text_source, status=row.status,
                        warnings=warnings, created_at=row.created_at)
