"""The only place that talks to the AI model.

    llm_json(instructions, data)   ask for a JSON answer (used by every feature)
    llm_read_pdf(instructions, pdf) let the AI read a PDF file itself, page by page like a picture
                                   (for scanned CVs; Gemini only)
    embed_texts(texts)             turn texts into vectors for the document search (RAG)
    check_connection()             the "Test AI connection" button

Works with Gemini (default), OpenAI or any OpenAI-compatible service: see LLM_* in core/config.py.
Every call writes one line to the log with the time and the tokens it used, for example
    AI call ok model=gemini-... 2.1s tokens in=1430 out=310 thinking=0
so you can see how much of the (free) Gemini quota a feature uses. Search the log for "tokens in=".
Returns None if anything goes wrong, so the caller can decide what to do.
last_error() then says why in plain words, so the screen can show it (no keys or CV text in it).
"""
import base64
import json
import logging
import re
import time

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


def _tokens(usage) -> str:
    """The token counts of an OpenAI-style answer, for the log ("?" when the service does not send them)."""
    if usage is None:
        return "tokens in=? out=?"
    details = getattr(usage, "completion_tokens_details", None)
    thinking = getattr(details, "reasoning_tokens", None) if details else None
    return f"tokens in={usage.prompt_tokens} out={usage.completion_tokens} thinking={thinking or 0}"


def last_error() -> str:
    """Why the most recent AI call failed, in plain words."""
    return _last_error or "unknown problem, see the backend terminal"


def _fail(reason: str) -> None:
    global _last_error
    _last_error = reason
    log.warning("AI call failed: %s", reason)


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

    started = time.time()
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
        else:
            log.info("AI call ok model=%s %.1fs %s", config.LLM_MODEL, time.time() - started, _tokens(response.usage))
        return answer
    except Exception as exc:  # network error, bad key, rate limit...
        name = type(exc).__name__
        _fail(REASONS.get(name, f"{name} from the AI service"))
        return None


def llm_read_pdf(instructions: str, pdf: bytes) -> str | None:
    """The AI looks at the PDF pages (also pictures of pages) and answers with plain text. None if it failed.
    The OpenAI-style address cannot take a PDF file, so this uses Gemini's own address (generateContent)."""
    if config.LLM_PROVIDER == "fake":
        from app.ai.fake_llm import fake_pdf_text
        return fake_pdf_text(pdf)
    if config.LLM_PROVIDER != "gemini":
        _fail("reading a PDF file with the AI works with Gemini only (LLM_PROVIDER=gemini)")
        return None
    problem = settings_problem()
    if problem:
        _fail(problem)
        return None

    import requests
    started = time.time()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.LLM_MODEL}:generateContent"
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}},
        {"text": instructions}]}]}
    try:
        response = requests.post(url, json=body, headers={"x-goog-api-key": config.LLM_API_KEY}, timeout=90)
    except Exception as exc:
        _fail(f"cannot reach the AI service ({type(exc).__name__})")
        return None
    if response.status_code != 200:
        _fail(f"the AI service answered with error {response.status_code} when reading the PDF")
        return None
    try:
        parts = response.json()["candidates"][0]["content"]["parts"]
        text = "\n".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError, ValueError):
        text = ""
    if not text:
        _fail("the AI could not read any text in the PDF")
        return None
    usage = response.json().get("usageMetadata", {})
    log.info("AI read a PDF model=%s %.1fs tokens in=%s out=%s thinking=%s", config.LLM_MODEL, time.time() - started,
             usage.get("promptTokenCount", "?"), usage.get("candidatesTokenCount", "?"), usage.get("thoughtsTokenCount", 0))
    return text


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
    started = time.time()
    try:
        response = _client().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
        tokens = getattr(response.usage, "prompt_tokens", "?") if getattr(response, "usage", None) else "?"
        log.info("embedding call ok model=%s texts=%d %.1fs tokens in=%s", config.EMBEDDING_MODEL, len(texts),
                 time.time() - started, tokens)
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
