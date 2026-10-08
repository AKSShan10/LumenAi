"""Request and response bodies for candidates."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SheetIn(BaseModel):
    """The link of the response sheet of one job's Google Form."""
    sheet_url: str = Field(max_length=500)

    @field_validator("sheet_url")
    @classmethod
    def check_link(cls, url: str) -> str:
        url = url.strip()
        if not url.startswith("https://") or " " in url:
            raise ValueError("Paste the link to the response sheet (it starts with https://docs.google.com/spreadsheets/)")
        return url


class CheckOut(BaseModel):
    """What is new in the response sheet after the job's checkpoint. Nothing is downloaded."""
    ok: bool
    message: str                     # one sentence for the interviewer
    new: int = 0                     # answers that are not fetched yet
    rows_read: int = 0               # how many rows of the sheet this check had to read (only those after the checkpoint)
    checkpoint_row: int = 1          # the last row of the sheet that is finished


class FetchOut(BaseModel):
    ok: bool
    message: str
    added: int = 0                   # new candidates saved now
    needs_review: int = 0            # of the added ones: how many a person must look at
    left_for_next_time: int = 0      # more answers than one click handles; click again


class UploadOut(BaseModel):
    ok: bool
    message: str
    candidate_id: int = 0


class CandidateOut(BaseModel):
    """One row of the candidate list. The CV text is not in it."""
    id: int                          # inside the code and the links only
    number: int                      # the number shown on the page: 1, 2, 3 ... inside this job
    job_id: int
    full_name: str
    email: str
    phone: str
    applied_at: str
    source: str                      # google_form | upload
    original_file_name: str
    has_file: bool                   # is the CV saved on this computer?
    saved_as: str                    # where it is saved, inside the storage folder
    cv_words: int
    screening_state: str = "waiting"  # waiting (not screened yet) | needs_review | included | excluded
    screening_reason: str = ""        # why (for needs_review it says what a person should look at)
    decided: bool = False             # the state comes from the interviewer's decision, not the system
    text_source: str = ""            # file (read by code) | ai_read (the AI read the PDF in the screening) | ""
    status: str
    warnings: list[str] = []
    created_at: datetime
