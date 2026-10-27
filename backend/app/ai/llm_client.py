"""The only place that talks to the AI model.

    llm_json(instructions, data)   ask for a JSON answer (used by every feature)
    llm_read_pdf(instructions, pdf) let the AI read a PDF file itself, page by page like a picture
                                   (for scanned CVs; Gemini only)
    embed_texts(texts)             turn texts into vectors for the document search (RAG)
    check_connection()             the "Test AI connection" button

Works with Gemini (default), OpenAI or any OpenAI-compatible service: see LLM_* in core/config.py.
    Gemini (LLM_PROVIDER=gemini)   Gemini's own address (generateContent). Its answer counts the thinking tokens
                                   separately (thoughtsTokenCount), so the log shows the real thinking.
    other providers                the OpenAI-style address (chat.completions)
Every call writes one line to the log with the time and the tokens it used, for example
    AI call ok model=gemini-... 2.1s tokens in=1430 out=310 thinking=250
so you can see how much of the (free) Gemini quota a feature uses. Search the log for "tokens in=".
Returns None if anything goes wrong, so the caller can decide what to do.
last_error() then says why in plain words, so the screen can show it (no keys or CV text in it).
"""
import base64
import json
import logging
import re
import time

from app.ai.model_choice import current_model
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
    if not thinking:
        # Gemini's OpenAI-style address does not fill reasoning_tokens, but it counts the thinking in total_tokens:
        # total = in + out + thinking, so the difference is the thinking.
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int):
            thinking = max(0, total - (usage.prompt_tokens or 0) - (usage.completion_tokens or 0))
    return f"tokens in={usage.prompt_tokens} out={usage.completion_tokens} thinking={thinking or 0}"


def last_error() -> str:
    """Why the most recent AI call failed, in plain words."""
    return _last_error or "unknown problem, see the backend terminal"


# Remembers why the last AI call failed (read by last_error) and writes a warning to the log
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


# ---------- Gemini's own address ----------

# The HTTP errors of Gemini's own address, and what they mean for a beginner
GEMINI_REASONS = {
    400: "the AI service rejected the request (check LLM_MODEL in .env)",
    401: "the AI service rejected the API key (check LLM_API_KEY in .env)",
    403: "the API key is not allowed to use this model or the API is not enabled",
    404: "the model name was not found (check LLM_MODEL in .env)",
    429: "too many requests or the free quota is used up (wait a minute and try again)",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}      # "too many requests" and temporary problems: wait and try again
RETRY_WAITS = (2, 4, 8, 16)                     # seconds to wait before each new try (like the OpenAI client did)


def _gemini_address(model: str) -> str:
    """Gemini's own address for one model. Made from LLM_BASE_URL (".../v1beta/openai/" -> ".../v1beta"),
    so a test can point it at a local fake service."""
    base = (config.LLM_BASE_URL or config.GEMINI_BASE_URL).rstrip("/")
    if base.endswith("/openai"):
        base = base[: -len("/openai")]
    return f"{base}/models/{model}:generateContent"


def _gemini_post(body: dict):
    """Sends one request to Gemini's own address. Tries again on "too many requests" and temporary errors.
    Returns the response, or raises the last connection error."""
    import requests
    for wait in (*RETRY_WAITS, None):
        try:
            response = requests.post(_gemini_address(current_model()), json=body,
                                     headers={"x-goog-api-key": config.LLM_API_KEY}, timeout=90)
        except (requests.ConnectionError, requests.Timeout):
            if wait is None:
                raise
            time.sleep(wait)
            continue
        if response.status_code not in RETRY_STATUSES or wait is None:
            return response
        time.sleep(wait)                              # → wait, then the same request once more


def _gemini_text(answer: dict) -> str:
    """The answer's text. Parts marked "thought" are the model's own thinking notes, not the answer."""
    try:
        parts = answer["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "".join(part.get("text", "") for part in parts if not part.get("thought"))


def gemini_tokens(usage: dict) -> str:
    """The token counts of a Gemini answer, for the log. thoughtsTokenCount is the thinking (0 when none)."""
    return (f"tokens in={usage.get('promptTokenCount', '?')} out={usage.get('candidatesTokenCount', 0)} "
            f"thinking={usage.get('thoughtsTokenCount', 0)}")


def _gemini_json(instructions: str, data) -> dict | None:
    """llm_json for Gemini: the same instructions and checks, through Gemini's own address."""
    started = time.time()
    body = {"systemInstruction": {"parts": [{"text": instructions + "\nReply with one JSON object only."}]},
            "contents": [{"role": "user", "parts": [{"text": data if isinstance(data, str) else json.dumps(data)}]}]}
    if config.LLM_TEMPERATURE is not None:
        body["generationConfig"] = {"temperature": config.LLM_TEMPERATURE}
    try:
        # A model sometimes sends broken JSON (e.g. a quote mark not escaped). Then it is asked once more.
        for attempt in (1, 2):
            response = _gemini_post(body)             # → the actual Gemini call (its own address)
            if response.status_code != 200:
                code = response.status_code
                _fail(GEMINI_REASONS.get(code, "the AI service had a temporary problem (try again)" if code >= 500
                                         else f"the AI service answered with error {code}"))
                return None
            answer = response.json()
            parsed = _parse_json(_gemini_text(answer))
            if parsed is not None:
                log.info("AI call ok model=%s %.1fs %s", current_model(), time.time() - started,
                         gemini_tokens(answer.get("usageMetadata") or {}))
                return parsed
            # finishReason "MAX_TOKENS" means the answer was cut off; only the reason is logged, never the text
            reason = ((answer.get("candidates") or [{}])[0] or {}).get("finishReason")
            log.warning("AI answer was not valid JSON (attempt %s, finish_reason=%s)", attempt, reason)
        _fail("the AI answered, but not with valid JSON (try again, or try another model)")
        return None
    except Exception as exc:                          # no connection, an answer that is not JSON at all ...
        _fail(f"cannot reach the AI service ({type(exc).__name__})")
        return None


# ---------- the OpenAI-style address (other providers) ----------

# Creates the OpenAI client pointed at LLM_BASE_URL (Gemini by default), with retries on rate limits
def _client():
    from openai import OpenAI
    # max_retries: waits and tries again on "too many requests" (free plans have a per-minute limit)
    return OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=90, max_retries=4)


# Sends instructions + data to the AI model and returns its JSON answer as a dict, or None on failure
def llm_json(instructions: str, data) -> dict | None:
    if config.LLM_PROVIDER == "fake":
        from app.ai.fake_llm import fake_answer
        return fake_answer(instructions, data)

    problem = settings_problem()
    if problem:
        _fail(problem)
        return None
    if config.LLM_PROVIDER == "gemini":
        return _gemini_json(instructions, data)      # → Gemini's own address: it reports the thinking tokens

    started = time.time()
    try:
        client = _client()
        options = {} if config.LLM_TEMPERATURE is None else {"temperature": config.LLM_TEMPERATURE}
        messages = [{"role": "system", "content": instructions + "\nReply with one JSON object only."},
                    {"role": "user", "content": data if isinstance(data, str) else json.dumps(data)}]
        # A model sometimes sends broken JSON (e.g. a quote mark not escaped). Then it is asked once more,
        # so one bad answer does not stop a whole workflow (the Q&A analysis makes six such calls at once).
        for attempt in (1, 2):
            response = client.chat.completions.create(  # → the actual AI call (OpenAI-compatible API)
                model=current_model(), messages=messages, **options)
            answer = _parse_json(response.choices[0].message.content or "")
            if answer is not None:
                log.info("AI call ok model=%s %.1fs %s", current_model(), time.time() - started,
                         _tokens(response.usage))
                return answer
            # finish_reason "length" means the answer was cut off; only the reason is logged, never the text
            log.warning("AI answer was not valid JSON (attempt %s, finish_reason=%s)", attempt,
                        response.choices[0].finish_reason)
        _fail("the AI answered, but not with valid JSON (try again, or try another model)")
        return None
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
    url = _gemini_address(current_model())
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
    log.info("AI read a PDF model=%s %.1fs tokens in=%s out=%s thinking=%s", current_model(), time.time() - started,
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
    info = {"provider": config.LLM_PROVIDER, "model": current_model()}
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
