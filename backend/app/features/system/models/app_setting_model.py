"""Table `app_setting`: settings the interviewer changes on the Settings page (not keys: those stay in .env).

    llm_model   the AI model chosen from LLM_MODEL_CHOICES; no row = LLM_MODEL from .env
"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"
    key: str = Field(primary_key=True)                # e.g. "llm_model"
    value: str = ""
    updated_by: str = ""                              # the interviewer's email
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
