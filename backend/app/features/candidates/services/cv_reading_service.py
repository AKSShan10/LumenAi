"""Checks on the text read out of a CV file.

    read_cv(filename, data)   -> CvText(text, source, problem)   plain code only, used when a CV is saved
    text_problem(text, pages) a sentence if the text looks incomplete (empty, very short, garbled), else ""
    looks_english(text)       is the CV written in English? (trainer: English CVs only)

When a CV is saved (fetched from the Google Form or uploaded), it is only read by plain code, so the list can
show the number of words and check that the applicant's name is in the CV. Nothing is sent to the AI then.
The full reading, with the AI reading a scanned PDF (OCR), is part of the screening workflow
(app/graphs/cv_screening_graph.py: parse_cv -> validate_extraction -> ocr_once).
"""
import re
from dataclasses import dataclass

from app.utils.file_text_utils import read_file_text

MIN_WORDS = 60                   # a real CV has far more words; fewer means parts are pictures or missing
MIN_WORDS_PER_PAGE = 25          # a page with fewer words is probably a scanned page
CHECKED_TYPES = (".pdf", ".docx", ".doc")      # plain .txt files are taken as they are

# Short words that almost every English text has. Used to tell an English CV from, say, a German one.
ENGLISH_WORDS = {"the", "and", "of", "in", "with", "for", "to", "a", "at", "as", "on", "my", "i", "is", "by", "from"}


@dataclass
class CvText:
    text: str
    source: str                  # file | ""
    problem: str                 # "" when the text looks complete


# Counts the words (2+ letters, no digits) in a text; used by text_problem
def _words(text: str) -> int:
    return len(re.findall(r"[^\W\d_]{2,}", text))


def text_problem(text: str, pages: int = 1) -> str:
    """A sentence for a person if the text looks incomplete, otherwise ""."""
    if not text.strip():
        return "No text was found in the file (a scanned PDF is a picture of the pages)."
    if "(cid:" in text:
        return "The text came out garbled (the PDF uses a font the reader does not understand)."
    visible = [c for c in text if not c.isspace()]
    if visible and sum(c.isalpha() for c in visible) / len(visible) < 0.5:
        return "The text came out garbled (more symbols than letters)."
    words = _words(text)
    if words < MIN_WORDS:
        return f"Only {words} words were found in the file. Parts of the CV may be pictures."
    if pages > 1 and words / pages < MIN_WORDS_PER_PAGE:
        return "Some pages have almost no text. They may be scanned pages."
    return ""


def looks_english(text: str) -> bool:
    """Mostly Latin letters, and the usual small English words appear (at least 3 of them, or 3% of all words)."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isascii() for c in letters) / len(letters) < 0.7:
        return False
    words = re.findall(r"[a-z]+", text.lower())
    common = sum(word in ENGLISH_WORDS for word in words)
    return common >= 3 or common >= 0.03 * len(words)


def read_cv(filename: str, data: bytes) -> CvText:
    """Plain code only: the text and a problem sentence for the list. The AI is not asked here."""
    try:
        text, pages = read_file_text(filename, data)
    except ValueError as problem:
        return CvText("", "", f"The CV text could not be read: {problem}")
    if not filename.lower().endswith(CHECKED_TYPES):
        return CvText(text, "file" if text else "", "" if text else "The CV file is empty.")
    problem = text_problem(text, pages)
    if problem:
        problem = "The CV text may be incomplete: " + problem
        if filename.lower().endswith(".pdf"):
            problem += " Screening will let the AI read the PDF."
    return CvText(text, "file" if text else "", problem)
