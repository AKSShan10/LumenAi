"""Response bodies for the transcript."""
from pydantic import BaseModel


class TranscriptTurnOut(BaseModel):
    """One finished sentence of the live transcript (interviewer only)."""
    id: int
    speaker: str                     # interviewer | candidate (from the microphone it came from)
    start_sec: float                 # seconds from the interview start
    end_sec: float
    text: str
