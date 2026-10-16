"""Table `transcript_turn`: one finished sentence of the live transcript.

The speaker is known from the microphone it came from (each browser sends its own), never guessed.
start_sec / end_sec are seconds from the start of the interview. The sound itself is never stored.
"""
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class TranscriptTurn(SQLModel, table=True):
    __tablename__ = "transcript_turn"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)               # the interview (interview_session)
    speaker: str                                      # interviewer | candidate
    start_sec: float = 0.0                            # when the sentence started, seconds from the interview start
    end_sec: float = 0.0                              # when it ended
    text: str = Field(sa_column=Column(Text))
