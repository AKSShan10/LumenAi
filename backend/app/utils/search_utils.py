"""Similarity helpers for the document search (RAG)."""
import math
import re


def cosine(a: list[float], b: list[float]) -> float:
    """How close two embedding vectors are: 1 = same direction, 0 = unrelated."""
    dot = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / size if size else 0.0


def word_overlap(a: str, b: str) -> float:
    """Share of the words in a that also appear in b (used when no embedding is available)."""
    words_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    words_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(words_a & words_b) / (len(words_a) or 1)
