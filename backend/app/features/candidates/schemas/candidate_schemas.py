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
    """What is in the response sheet, compared with what is already saved. Nothing is downloaded."""
    ok: bool
    message: str                     # one sentence for the interviewer
    in_sheet: int = 0                # form answers in the sheet
    new: int = 0                     # answers that are not fetched yet
    already_fetched: int = 0


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
    id: int
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
    status: str
    warnings: list[str] = []
    created_at: datetime
