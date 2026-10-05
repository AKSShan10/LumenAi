"""The only place that talks to the AI model.

    llm_json(instructions, data)   ask for a JSON answer (used by every feature)
    embed_texts(texts)             turn texts into vectors for the document search (RAG)
    check_connection()             the "Test AI connection" button

Works with Gemini (default), OpenAI or any OpenAI-compatible service: see LLM_* in core/config.py.
Returns None if anything goes wrong, so the caller can decide what to do.
last_error() then says why in plain words, so the screen can show it (no keys or CV text in it).
"""
import json
import logging
import re

from app.core import config

log = logging.getLogger("llm")
_last_error = ""

# The error names the OpenAI client uses, and what they mean for a beginner.
REASONS = {
    "AuthenticationError": "the AI service rejected the API key (check LLM_API_KEY in .env)",
    "PermissionDeniedError": "the API key is not allowed to use this model or the API is not enabled",
    "NotFoundError": "the model name was not found (check LLM_MODEL in .env)",
    "BadRequestError": "the AI service rejected the request (check LLM_MODEL in .env)",
    "RateLimitError": "too many requests or the free quota is used up (wait a minute and try again)",
    "APIConnectionError": "cannot reach the AI service (check the internet connection and LLM_BASE_URL)",
    "APITimeoutError": "the AI service took too long to answer (try again)",
    "InternalServerError": "the AI service had a temporary problem (try again)",
}


def last_error() -> str:
    """Why the most recent AI call failed, in plain words."""
    return _last_error or "unknown problem, see the backend terminal"


def _fail(reason: str) -> None:
    global _last_error
    _last_error = reason
    log.warning("LLM call failed: %s", reason)


def settings_problem() -> str:
    """A missing or placeholder setting, found before calling the AI service."""
    if not config.LLM_API_KEY or config.LLM_API_KEY in ("replace-me", "your-gemini-key"):
        return "LLM_API_KEY is not set in .env"
    if not config.LLM_MODEL:
        return "LLM_MODEL is not set in .env"
    return ""


def _client():
    from openai import OpenAI
    # max_retries: waits and tries again on "too many requests" (free plans have a per-minute limit)
    return OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=90, max_retries=4)


def llm_json(instructions: str, data) -> dict | None:
    if config.LLM_PROVIDER == "fake":
        from app.ai.fake_llm import fake_answer
        return fake_answer(instructions, data)

    problem = settings_problem()
    if problem:
        _fail(problem)
        return None

    try:
        client = _client()
        options = {} if config.LLM_TEMPERATURE is None else {"temperature": config.LLM_TEMPERATURE}
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": instructions + "\nReply with one JSON object only."},
                {"role": "user", "content": data if isinstance(data, str) else json.dumps(data)},
            ],
            **options,
        )
        answer = _parse_json(response.choices[0].message.content or "")
        if answer is None:
            _fail("the AI answered, but not with valid JSON (try again, or try another model)")
        return answer
    except Exception as exc:  # network error, bad key, rate limit...
        name = type(exc).__name__
        _fail(REASONS.get(name, f"{name} from the AI service"))
        return None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Vectors for the document search. None if it failed (the search then compares words instead)."""
    if not texts:
        return []
    if config.LLM_PROVIDER == "fake":
        from app.ai.fake_llm import fake_embedding
        return [fake_embedding(t) for t in texts]
    problem = settings_problem()
    if problem:
        _fail(problem)
        return None
    try:
        response = _client().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
    except Exception as exc:
        name = type(exc).__name__
        _fail(REASONS.get(name, f"{name} from the embedding service"))
        return None


def check_connection() -> dict:
    """One tiny test call, used by the 'Test AI connection' button."""
    info = {"provider": config.LLM_PROVIDER, "model": config.LLM_MODEL}
    if config.LLM_PROVIDER == "fake":
        return {**info, "ok": True, "message": "Offline fake AI. Set LLM_PROVIDER=gemini for real AI."}
    answer = llm_json('Return {"ok": true}.', "ping")
    if answer is not None:
        return {**info, "ok": True, "message": "The AI service answered correctly."}
    return {**info, "ok": False, "message": "Not working: " + last_error()}


def _parse_json(text: str) -> dict | None:
    """Models sometimes wrap JSON in ```json fences. Take the part between the first { and last }."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
