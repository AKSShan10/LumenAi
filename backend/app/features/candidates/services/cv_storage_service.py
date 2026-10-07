"""CV files on this computer, and the candidates that are added by hand.

    save_cv_file()       writes one CV into the storage folder and returns where it is
    cv_file()            the saved file of one candidate (to open or download it)
    delete_candidate()   removes the candidate and the saved file
    add_uploaded_cv()    manual upload: one file becomes one candidate
    candidate_out()      the list row shown on the Candidates page

Where files go:
    <STORAGE_DIR>/cvs/job_<job id>/google_form/candidate_<number>_<name>.<ext>     fetched from the Google Form
    <STORAGE_DIR>/cvs/job_<job id>/uploaded/candidate_<number>_<name>.<ext>        uploaded by hand

What keeps two CVs apart is the candidate's NUMBER. It is the row's id in the database, and no two candidates
ever share one, in any job. So two people who both send "CV.pdf", or two people with the same name, get two
different files. The name in the file name is only there so a person can read the folder; the code never
uses it to find a file. The exact place of each file is saved in candidate.file_path.
The storage folder holds real CVs: it is in .gitignore and must never be committed.
"""
import hashlib
import logging
import os
import re
from pathlib import Path

from sqlmodel import Session, select

from app.core import config
from app.features.candidates.models import Candidate
from app.features.candidates.schemas import CandidateOut, UploadOut
from app.features.jobs.models import Job
from app.utils.file_text_utils import text_from_file

log = logging.getLogger("candidates")

BACKEND_DIR = Path(__file__).resolve().parents[4]
MAX_FILE_BYTES = 5 * 1024 * 1024
ALLOWED = (".pdf", ".docx", ".txt")
FOLDERS = {"google_form": "google_form", "upload": "uploaded"}     # one folder per way a CV arrived


def storage_dir() -> Path:
    """STORAGE_DIR from .env; a path that does not start at the disk root is inside backend/."""
    path = Path(config.STORAGE_DIR)
    return path if path.is_absolute() else BACKEND_DIR / path


def _for_file_name(full_name: str) -> str:
    """"Rahim Uddin" -> "rahim-uddin". Only plain letters and digits are kept; anything else may be empty."""
    return re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")[:40]


def save_cv_file(candidate: Candidate, original_name: str, data: bytes) -> str:
    """Writes the file and returns its place inside the storage folder (saved in candidate.file_path)."""
    extension = os.path.splitext(original_name)[1].lower()[:10]
    name = _for_file_name(candidate.full_name)
    file_name = f"candidate_{candidate.id}_{name}{extension}" if name else f"candidate_{candidate.id}{extension}"
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
    session.delete(candidate)
    session.commit()


def add_uploaded_cv(session: Session, job: Job, filename: str, data: bytes,
                    full_name: str = "", email: str = "", phone: str = "") -> UploadOut:
    """Manual upload, for a CV the organization received in another way. The name, email and phone are
    whatever the interviewer typed with this file (they may be empty)."""
    if os.path.splitext(filename)[1].lower() not in ALLOWED:
        return UploadOut(ok=False, message=f"{filename}: only PDF, DOCX and TXT files can be uploaded.")
    if len(data) > MAX_FILE_BYTES:
        return UploadOut(ok=False, message=f"{filename}: the file is larger than 5 MB.")

    key = "upload:" + hashlib.sha256(data).hexdigest()        # the same file twice for one job is skipped
    if session.exec(select(Candidate).where(Candidate.job_id == job.id, Candidate.source_key == key)).first():
        return UploadOut(ok=False, message=f"{filename}: this exact file was already added to this job.")

    warnings, cv_text = [], ""
    try:
        cv_text = text_from_file(filename, data)
    except ValueError as problem:
        warnings.append("The CV could not be read: " + str(problem))
    if not full_name.strip():
        warnings.append("No name was given with this file")

    candidate = Candidate(job_id=job.id, full_name=full_name.strip(), email=email.strip(), phone=phone.strip(),
                          source="upload", source_key=key, original_file_name=filename[:200], cv_text=cv_text,
                          status="new" if cv_text else "needs_review", warnings=warnings)
    session.add(candidate)
    session.flush()                                   # gives the candidate its number, needed for the file name
    candidate.file_path = save_cv_file(candidate, filename, data)
    session.commit()
    log.info("cv uploaded job=%s candidate=%s status=%s", job.id, candidate.id, candidate.status)
    return UploadOut(ok=True, message=f"{filename} was added.", candidate_id=candidate.id)


def candidate_out(row: Candidate) -> CandidateOut:
    return CandidateOut(id=row.id, job_id=row.job_id, full_name=row.full_name, email=row.email, phone=row.phone,
                        applied_at=row.applied_at, source=row.source, original_file_name=row.original_file_name,
                        has_file=cv_file(row) is not None, saved_as=row.file_path, cv_words=len(row.cv_text.split()), status=row.status,
                        warnings=row.warnings or [], created_at=row.created_at)
