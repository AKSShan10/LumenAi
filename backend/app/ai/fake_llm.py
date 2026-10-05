"""An offline stand-in for the AI model, used when LLM_PROVIDER=fake.

Use it for tests and for trying the app without an API key. Use a real model for the actual demo.
Each feature adds its own fake answer here, chosen by the prompt it sends, for example:

    if instructions == JOB_DESCRIPTION_PROMPT:
        return {"description": "..."}
"""
import hashlib
import math
import re


def fake_answer(instructions: str, data) -> dict:
    return {"ok": True}


def fake_embedding(text: str, size: int = 64) -> list[float]:
    """Words hashed into a small vector, so similar texts get similar vectors (tests only)."""
    vector = [0.0] * size
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % size] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]
