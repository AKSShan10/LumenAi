"""Speech-to-text for the live transcript. One microphone = one stream = one speaker.

    stt_problem()                          what is missing in .env, or "" when speech-to-text is set up
    transcribe(audio, on_sentence, speaker)  reads audio from the queue until None, calls on_sentence for each
                                           finished sentence: await on_sentence(text, start_sec, end_sec)
    stt_check()                            the Settings button: is the key accepted? sends no audio

The queue holds: bytes = 16 kHz, 16-bit mono sound from the browser; str = a test sentence (fake only); None = end.
start_sec / end_sec are seconds from the moment the stream opened (the router adds the time since the interview
start). The sound is passed on and forgotten: it is never stored.

Providers (STT_PROVIDER in .env):
    deepgram   Deepgram live over a WebSocket. Deepgram sends pieces of a sentence; they are joined into one
               sentence when Deepgram says the person stopped talking (speech_final or UtteranceEnd).
    fake       no service: a test sentence for every few seconds of sound (tests and demos). Not real speech.
"""
import asyncio
import json
from urllib.parse import urlencode

import httpx

from app.core import config

SAMPLE_RATE = 16000
BYTES_PER_SEC = SAMPLE_RATE * 2          # 16-bit = 2 bytes per sample, one channel
FAKE_EVERY_SEC = 6                       # fake: one test sentence for every 6 seconds of sound
DEEPGRAM_CHECK_URL = "https://api.deepgram.com/v1/projects"
TIMEOUT_SEC = 10

FAKE_LINES = {
    "interviewer": ["Thank you for joining. Could you tell me about your last project?",
                    "How did you design the database for that project?",
                    "What would you do if an API call became slow in production?",
                    "Do you have any questions for us?"],
    "candidate": ["I built a booking service with FastAPI and PostgreSQL.",
                  "I used one table per entity and added indexes for the slow searches.",
                  "I would check the logs first, then measure the slow query and add caching if needed.",
                  "Yes, how does the team review code?"],
}


class SttError(Exception):
    """Speech-to-text could not start or stopped. The message is safe to show (never the key)."""


def stt_problem() -> str:
    if config.STT_PROVIDER == "fake":
        return ""
    if config.STT_PROVIDER != "deepgram":
        return f"STT_PROVIDER={config.STT_PROVIDER} is not known (use deepgram or fake)"
    if not config.DEEPGRAM_API_KEY:
        return "Speech-to-text is not set up: DEEPGRAM_API_KEY is empty in .env"
    return ""


async def transcribe(audio: asyncio.Queue, on_sentence, speaker: str) -> None:
    """Runs until the queue gives None (the browser closed the stream)."""
    if config.STT_PROVIDER == "fake":
        await _fake(audio, on_sentence, speaker)
    else:
        await _deepgram(audio, on_sentence)


# ---------- fake: test sentences, no service ----------

async def _fake(audio: asyncio.Queue, on_sentence, speaker: str) -> None:
    heard, said, next_at = 0.0, 0, FAKE_EVERY_SEC
    lines = FAKE_LINES.get(speaker, FAKE_LINES["candidate"])
    while True:
        item = await audio.get()
        if item is None:
            return
        if isinstance(item, str):                       # a test sentence sent as text
            length = max(1.0, len(item.split()) * 0.4)
            await on_sentence(item, heard, heard + length)
            heard += length
            continue
        heard += len(item) / BYTES_PER_SEC
        if heard >= next_at:                            # every 6 seconds of sound: the next test sentence
            await on_sentence(lines[said % len(lines)], next_at - 4, next_at)
            said, next_at = said + 1, next_at + FAKE_EVERY_SEC


# ---------- Deepgram live ----------

def _deepgram_address() -> str:
    settings = {"model": config.DEEPGRAM_MODEL, "language": config.DEEPGRAM_LANGUAGE, "encoding": "linear16",
                "sample_rate": SAMPLE_RATE, "channels": 1, "punctuate": "true", "smart_format": "true",
                "interim_results": "true",       # needed for utterance_end_ms
                "endpointing": 300,              # 0.3 s of silence = the end of a piece
                "utterance_end_ms": 1000}        # 1 s without words = the person stopped talking
    return f"{config.DEEPGRAM_URL}?{urlencode(settings)}"


async def _deepgram(audio: asyncio.Queue, on_sentence) -> None:
    import websockets                                    # only needed when Deepgram is used
    try:
        connection = await websockets.connect(_deepgram_address(), open_timeout=TIMEOUT_SEC,
                                              additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"})
    except websockets.InvalidStatus as problem:
        code = problem.response.status_code
        raise SttError("Deepgram did not accept the key (check DEEPGRAM_API_KEY)" if code in (401, 403)
                       else f"Deepgram refused the stream (HTTP {code})") from None
    except Exception as problem:                         # never str(problem): it could contain the address with settings
        raise SttError(f"could not reach Deepgram ({type(problem).__name__})") from None

    # → browser sound to Deepgram, until the browser closes the stream
    async def send_sound():
        while True:
            item = await audio.get()
            if item is None:
                await connection.send(json.dumps({"type": "CloseStream"}))   # Deepgram sends the last words, then closes
                return
            if isinstance(item, bytes):
                await connection.send(item)

    sender = asyncio.create_task(send_sound())
    pieces, first, last = [], 0.0, 0.0
    try:
        async for message in connection:                 # Deepgram's answers, until it closes
            data = json.loads(message)
            if data.get("type") == "Results" and data.get("is_final"):
                text = data["channel"]["alternatives"][0].get("transcript", "").strip()
                if text:
                    if not pieces:
                        first = data.get("start", 0.0)
                    pieces.append(text)
                    last = data.get("start", 0.0) + data.get("duration", 0.0)
                if not data.get("speech_final"):
                    continue
            elif data.get("type") != "UtteranceEnd":
                continue
            if pieces:                                   # the person stopped talking: one finished sentence
                await on_sentence(" ".join(pieces), first, last)
                pieces = []
        if pieces:                                       # the stream ended in the middle of a sentence
            await on_sentence(" ".join(pieces), first, last)
    except websockets.ConnectionClosedError:
        raise SttError("Deepgram closed the stream") from None
    finally:
        sender.cancel()
        await connection.close()


# ---------- the Settings button ----------

def stt_check() -> dict:
    """Is speech-to-text set up, and does Deepgram accept the key? Sends no sound."""
    if config.STT_PROVIDER == "fake":
        return {"ok": True, "message": "Fake speech-to-text is on (STT_PROVIDER=fake): test sentences, not real speech."}
    problem = stt_problem()
    if problem:
        return {"ok": False, "message": problem + "."}
    try:
        answer = httpx.get(DEEPGRAM_CHECK_URL, timeout=TIMEOUT_SEC,
                           headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"})
    except Exception as problem:                         # never str(problem)
        return {"ok": False, "message": f"Could not reach Deepgram ({type(problem).__name__}). Check the internet connection."}
    if answer.status_code in (401, 403):
        return {"ok": False, "message": "Deepgram did not accept the key. Check DEEPGRAM_API_KEY in .env."}
    if answer.status_code != 200:
        return {"ok": False, "message": f"Deepgram answered with HTTP {answer.status_code}. Try again later."}
    return {"ok": True, "message": f"Speech-to-text is set up (Deepgram, model {config.DEEPGRAM_MODEL})."}
