"""Tables of the Q&A analysis (F5): what the interview showed, made from the transcript after the call.

    qa_analysis   one row per interview: running | done | failed, the interview score, covered / uncovered requirements
    qa_item       one row per question and answer: the four grades with reasons, the quote with its time, references
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class QaAnalysis(SQLModel, table=True):
    __tablename__ = "qa_analysis"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True, unique=True)  # the interview (interview_session); one analysis each
    status: str = "running"                           # running | done | failed
    error: str = Field(default="", sa_column=Column(Text))    # why it failed, in plain words
    interview_score: Optional[float] = None           # average score of the job-related answers (0-100)
    covered: list = Field(default_factory=list, sa_column=Column(JSON))     # job requirements the answers showed
    uncovered: list = Field(default_factory=list, sa_column=Column(JSON))   # job requirements they did not show
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QaItem(SQLModel, table=True):
    __tablename__ = "qa_item"
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)               # the interview
    position: int = 0                                 # the order in the interview (1, 2, 3 ...)
    question: str = Field(default="", sa_column=Column(Text))
    answer: str = Field(default="", sa_column=Column(Text))        # the candidate's own words from the transcript
    job_related: bool = True                          # False = small talk: kept, but not graded
    split_from_multi_part: bool = False               # one part of a question that asked several things
    # The four grades: 0 / 25 / 50 / 75 / 100 (None for small talk)
    relevance: Optional[int] = None
    accuracy: Optional[int] = None
    completeness: Optional[int] = None
    articulation: Optional[int] = None                # how clear the answer's words are (never voice or fluency)
    score: Optional[float] = None                     # the average of the four grades
    reasons: dict = Field(default_factory=dict, sa_column=Column(JSON))     # {"relevance": "one sentence", ...}
    evidence_quote: str = Field(default="", sa_column=Column(Text))         # checked: really in the answer
    evidence_time: Optional[float] = None             # when it was said, seconds from the interview start
    requirements: list = Field(default_factory=list, sa_column=Column(JSON))  # the job requirements it tests
    references: list = Field(default_factory=list, sa_column=Column(JSON))    # company documents used for accuracy
