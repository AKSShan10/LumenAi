"""Tables of the Q&A analysis (F5): what the interview showed, made from the transcript after the call.

    qa_analysis   one row per interview: running | done | failed, the interview score, covered / uncovered requirements,
                  the scorecard (F9: six dimensions with score, reason and the best checked quote)
    qa_item       one row per question and answer: the six grades with reasons, the quote with its time, references
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
    interview_score: Optional[float] = None           # the average of the six scorecard dimensions (0-100)
    covered: list = Field(default_factory=list, sa_column=Column(JSON))     # job requirements the answers showed
    uncovered: list = Field(default_factory=list, sa_column=Column(JSON))   # job requirements they did not show
    # F9 scorecard: [{"key", "name", "score", "reason", "quote", "time"}] for the six dimensions ([] = analysed before F9)
    scorecard: list = Field(default_factory=list, sa_column=Column(JSON))
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
    # The six grades: 0 to 100 (None for small talk)
    relevance: Optional[int] = None
    accuracy: Optional[int] = None
    completeness: Optional[int] = None
    articulation: Optional[int] = None                # how clear the answer's words are (never voice or fluency)
    problem_solving: Optional[int] = None             # how the answer works through a problem (F9)
    depth: Optional[int] = None                       # hands-on experience shown (F9)
    score: Optional[float] = None                     # the average of the six grades
    reasons: dict = Field(default_factory=dict, sa_column=Column(JSON))     # {"relevance": "one sentence", ...}
    evidence_quote: str = Field(default="", sa_column=Column(Text))         # checked: really in the answer
    evidence_time: Optional[float] = None             # when it was said, seconds from the interview start
    requirements: list = Field(default_factory=list, sa_column=Column(JSON))  # the job requirements it tests
    references: list = Field(default_factory=list, sa_column=Column(JSON))    # company documents used for accuracy
    follow_up: str = Field(default="", sa_column=Column(Text))  # a question to ask next for what the answer missed
