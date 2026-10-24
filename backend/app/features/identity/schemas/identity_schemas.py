"""Request and response bodies of the identity check (F7)."""
from typing import Literal, Optional

from pydantic import BaseModel


class IdentityOut(BaseModel):
    session_id: int
    candidate_id: int
    photo_on_record: bool = False      # a photo from the application exists
    face_status: str = ""              # the photo: ready | no_face | several_faces | no_photo ...
    result: str = ""                   # "" (not checked) | confident | low | no_match | no_face | no_photo | ...
    similarity: Optional[float] = None
    better_match: Optional[dict] = None  # another record that matches as well or better: {candidate_id, name, ...}
    message: str = ""
    checked_at: Optional[str] = None
    decision: str = ""                 # "" | confirmed | rejected (always the interviewer's)
    decided_by: str = ""
    decided_at: Optional[str] = None
    same_person_at: float              # the thresholds, so the page can explain the result
    confident_at: float


class DecisionIn(BaseModel):
    decision: Literal["confirmed", "rejected", ""]
