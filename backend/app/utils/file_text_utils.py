"""Reads the text out of an uploaded file: PDF, Word (DOCX and the old DOC) or plain text.

    read_file_text(filename, data)   the text and the number of pages. Used for CVs (see cv_reading_service.py)
    text_from_file(filename, data)   the text only; an empty file is an error. Used for company documents

Which tool reads which file:
    .pdf    pypdf            a scanned page (a picture) has no text: the text comes back empty or very short
    .docx   python-docx      normal paragraphs AND tables, text boxes, headers and footers, in page order
    .doc    antiword         the old Word 97-2003 format. antiword is a small program that is installed in the
                             Docker image (see backend/Dockerfile). Without it a .doc file cannot be read.
    .txt    plain Python
"""
import io
import re
import shutil
import subprocess

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

ALLOWED_TYPES = (".pdf", ".docx", ".doc", ".txt")
MAX_FILE_BYTES = 5 * 1024 * 1024          # 5 MB


def text_from_file(filename: str, data: bytes) -> str:
    """The text of the file. Raises ValueError with a message for the user if the file cannot be used."""
    text, _pages = read_file_text(filename, data)
    if not text:
        raise ValueError("No text was found in the file. A scanned PDF (a picture of a page) cannot be read.")
    return text


def read_file_text(filename: str, data: bytes) -> tuple[str, int]:
    """(text, pages). The text may be empty, for example for a scanned PDF.
    Raises ValueError with a message for the user if the file is of the wrong type or damaged."""
    name = filename.lower()
    if not name.endswith(ALLOWED_TYPES):
        raise ValueError("Please upload a PDF, DOCX, DOC or TXT file.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("The file is too large (5 MB at most).")
    if name.endswith(".doc"):
        text, pages = _doc_text(data), 1          # checked first: ".doc" is also the start of ".docx"
    else:
        try:
            if name.endswith(".pdf"):
                pdf_pages = PdfReader(io.BytesIO(data)).pages
                text, pages = "\n".join(page.extract_text() or "" for page in pdf_pages), len(pdf_pages)
            elif name.endswith(".docx"):
                text, pages = _docx_text(data), 1
            else:
                text, pages = data.decode("utf-8", errors="ignore"), 1
        except Exception:
            raise ValueError("The file could not be read. It may be damaged or protected by a password.")
    return text.replace("\x00", "").strip(), pages       # PostgreSQL does not accept the \x00 character


def _paragraph_lines(element) -> list[str]:
    """The text of every paragraph inside an XML element, in page order. This includes the paragraphs inside
    table cells and text boxes. A text box is stored twice in the file (a new and an old way of drawing it);
    the old copy sits inside <mc:Fallback> and is skipped, so nothing is read twice."""
    lines = []
    for paragraph in element.iter(qn("w:p")):
        if any(parent.tag.endswith("}Fallback") for parent in paragraph.iterancestors()):
            continue
        text = "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
        if text.strip():
            lines.append(text.strip())
    return lines


# Reads a DOCX file: header, body (with tables and text boxes) and footer lines, without repeats
def _docx_text(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    lines = []
    for section in document.sections:             # headers often hold the name, email and phone
        lines += _paragraph_lines(section.header._element)
    lines += _paragraph_lines(document.element.body)
    for section in document.sections:
        lines += _paragraph_lines(section.footer._element)
    return "\n".join(dict.fromkeys(lines))         # a header repeated by several sections is kept once


# Reads an old Word .doc file with the antiword program; raises ValueError if it is missing or fails
def _doc_text(data: bytes) -> str:
    program = shutil.which("antiword")
    if not program:
        raise ValueError("Old Word .doc files need the program antiword, which is installed in the Docker image. "
                         "Run the backend in Docker, or save the file as DOCX or PDF.")
    try:
        result = subprocess.run([program, "-w", "0", "-"], input=data, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise ValueError("The .doc file took too long to read.")
    if result.returncode != 0:
        raise ValueError("The .doc file could not be read. It may be damaged, or it is not a real Word 97-2003 file.")
    text = result.stdout.decode("utf-8", errors="ignore")
    return re.sub(r"[ \t]{2,}", " ", text)          # antiword pads table cells with many spaces
