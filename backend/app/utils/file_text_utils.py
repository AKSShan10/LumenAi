"""Reads the text out of an uploaded file (PDF, Word or plain text).

Used for company documents now, and for CVs later.
"""
import io

from docx import Document
from pypdf import PdfReader

ALLOWED_TYPES = (".pdf", ".docx", ".txt")
MAX_FILE_BYTES = 5 * 1024 * 1024          # 5 MB


def text_from_file(filename: str, data: bytes) -> str:
    """The text of the file. Raises ValueError with a message for the user if the file cannot be used."""
    name = filename.lower()
    if not name.endswith(ALLOWED_TYPES):
        raise ValueError("Please upload a PDF, DOCX or TXT file.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("The file is too large (5 MB at most).")
    try:
        if name.endswith(".pdf"):
            pages = PdfReader(io.BytesIO(data)).pages
            text = "\n".join(page.extract_text() or "" for page in pages)
        elif name.endswith(".docx"):
            text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception:
        raise ValueError("The file could not be read. It may be damaged or protected by a password.")
    text = text.replace("\x00", "").strip()      # PostgreSQL does not accept this character
    if not text:
        raise ValueError("No text was found in the file. A scanned PDF (a picture of a page) cannot be read.")
    return text
