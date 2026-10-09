"""Table `candidate`: one application to one job, and where that person's CV file is saved."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class Candidate(SQLModel, table=True):
    """The name, email, phone and CV of a Google Form application all come from ONE answer of the job's Google Form.
    The row below keeps them together, so a CV can never end up under another person's name."""
    __tablename__ = "candidate"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    # The candidate's number INSIDE its job: 1, 2, 3 ... for every job on its own. Shown on the page and used in
    # the file name. (The id above counts over all jobs and is only used inside the code and the links.)
    number: int = 0
    full_name: str = ""
    email: str = ""
    phone: str = ""
    applied_at: str = ""                              # when the form was sent (the answer's time from Google Forms)
    source: str = "google_form"                       # google_form | upload (added by hand)
    # What makes this application unique inside its job: the Google Drive id of the CV (form), or a fingerprint
    # of the file (upload). Fetching or uploading again skips a key that is already saved.
    source_key: str = Field(index=True)
    drive_file_id: str = ""                           # Google Drive id of the CV (form applications only)
    original_file_name: str = ""                      # the name the applicant gave the file; only shown, never used to match
    file_path: str = ""                               # where the CV is saved, inside the storage folder: cvs/job_3/google_form/candidate_12_rahim-uddin.pdf
    cv_text: str = Field(default="", sa_column=Column(Text))      # the text read out of the CV (used by the screening)
    text_source: str = ""                             # file (read by code) | ai_read (the AI read the PDF) | "" (no text)
    read_problem: str = ""                            # why the text may be incomplete; "" when it looks complete
    status: str = "new"                               # new | needs_review (a person must look at it)
    warnings: list = Field(default_factory=list, sa_column=Column(JSON))   # plain sentences, shown on the page
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
