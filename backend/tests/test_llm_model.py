"""Choosing the AI model on the Settings page: only models from LLM_MODEL_CHOICES in .env; the next AI call uses it."""
import pytest

from app.ai import llm_client
from app.ai.model_choice import current_model
from app.core import config


@pytest.fixture
def choices(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setattr(config, "LLM_MODEL_CHOICES", ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"])
    yield
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.system.models import AppSetting
    with Session(engine) as session:                   # other tests use the .env model
        row = session.get(AppSetting, "llm_model")
        if row:
            session.delete(row)
            session.commit()


def test_the_interviewer_chooses_an_allowed_model(client, anonymous, choices):
    info = client.get("/api/llm-model").json()
    assert info == {"model": "gemini-3.5-flash", "default": "gemini-3.5-flash",
                    "choices": ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]}
    chosen = client.put("/api/llm-model", json={"model": "gemini-3.1-flash-lite"}).json()
    assert chosen["model"] == "gemini-3.1-flash-lite" and current_model() == "gemini-3.1-flash-lite"
    assert llm_client.check_connection()["model"] == "gemini-3.1-flash-lite"      # used at once, no restart

    wrong = client.put("/api/llm-model", json={"model": "gemini-2.5-flash"})
    assert wrong.status_code == 400 and "LLM_MODEL_CHOICES" in wrong.json()["detail"]
    assert anonymous.put("/api/llm-model", json={"model": "gemini-3.6-flash"}).status_code == 401


def test_a_model_removed_from_the_list_falls_back_to_the_default(client, choices, monkeypatch):
    client.put("/api/llm-model", json={"model": "gemini-3.6-flash"})
    monkeypatch.setattr(config, "LLM_MODEL_CHOICES", ["gemini-3.5-flash", "gemini-3.1-flash-lite"])   # .env changed
    assert current_model() == "gemini-3.5-flash"
