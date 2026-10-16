"""Request and response bodies for the interview helper."""
from datetime import datetime

from pydantic import BaseModel, Field


class QuestionsIn(BaseModel):
    """"Suggest questions": an optional topic, e.g. "Docker" or "teamwork" ("" = the AI chooses)."""
    topic: str = Field(default="", max_length=200)


class HelperChatIn(BaseModel):
    """One message from the interviewer to the helper."""
    text: str = Field(min_length=1, max_length=1000)


class SuggestedQuestion(BaseModel):
    question: str                    # what to ask
    requirement: str                 # the job requirement it tests, e.g. "PostgreSQL"
    why: str                         # why it is worth asking this candidate
    model_answer: str                # what a strong answer would contain (a reference, not a score)
    source: str = ""                 # the company note it is based on ("" = none)


class HelperMessageOut(BaseModel):
    id: int
    role: str                        # interviewer | helper
    kind: str                        # chat | questions
    text: str
    questions: list[SuggestedQuestion] = []
    sources: list[str] = []          # company notes given to / used by the AI ([] = no matching company document)
    created_at: datetime
