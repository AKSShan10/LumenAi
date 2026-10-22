"""Which AI model is used: the one chosen on the Settings page, or LLM_MODEL from .env.

    current_model()             the model every AI call uses now (read on each call, so a change works at once)
    model_info()                the chosen model, the default and the allowed list (Settings page)
    choose_model(name, by)      saves the choice; only names from LLM_MODEL_CHOICES in .env are allowed

The API key never changes here: it stays in .env.
"""
from sqlmodel import Session

from app.core import config

KEY = "llm_model"


def current_model() -> str:
    """The chosen model if it is still in the allowed list; otherwise LLM_MODEL from .env."""
    try:
        from app.core.database import engine
        from app.features.system.models import AppSetting
        with Session(engine) as session:
            row = session.get(AppSetting, KEY)
    except Exception:                                  # no database yet (e.g. a script): the .env model
        return config.LLM_MODEL
    return row.value if row and row.value in config.LLM_MODEL_CHOICES else config.LLM_MODEL


def model_info() -> dict:
    return {"model": current_model(), "default": config.LLM_MODEL, "choices": config.LLM_MODEL_CHOICES}


def choose_model(session: Session, name: str, by: str) -> dict:
    from fastapi import HTTPException
    from app.features.system.models import AppSetting
    from app.utils.datetime_utils import utc_now
    if name not in config.LLM_MODEL_CHOICES:
        raise HTTPException(400, f"\"{name}\" is not in LLM_MODEL_CHOICES in .env.")
    row = session.get(AppSetting, KEY) or AppSetting(key=KEY)
    row.value, row.updated_by, row.updated_at = name, by, utc_now()
    session.add(row)
    session.commit()
    return model_info()
