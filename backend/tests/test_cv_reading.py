"""Reading CV files: no part of a CV may be lost silently. Made-up CVs only (tests/sample_cvs)."""
import shutil
from pathlib import Path

import pytest

from app.features.candidates.services.cv_reading_service import looks_english, read_cv, text_problem
from app.utils.file_text_utils import read_file_text

SAMPLES = Path(__file__).parent / "sample_cvs"
needs_antiword = pytest.mark.skipif(not shutil.which("antiword"), reason="antiword is installed in the Docker image only")


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


# ---------- reading the file (plain code) ----------

def test_docx_tables_and_header_are_read():
    text, _ = read_file_text("cv.docx", sample("karima_tables.docx"))
    for part in ("Karima Akter", "Python, FastAPI, PostgreSQL, Docker",          # a normal paragraph and a table cell
                 "BSc in Computer Science and Engineering", "karima@example.com"):   # a table cell and the page header
        assert part in text


@needs_antiword
def test_old_word_doc_is_read():
    text, _ = read_file_text("cv.doc", sample("karima_tables.doc"))
    assert "Karima Akter" in text and "PostgreSQL" in text and "  " not in text   # the table padding is removed


def test_doc_without_antiword_is_explained(monkeypatch):
    monkeypatch.setattr("app.utils.file_text_utils.shutil.which", lambda name: None)
    with pytest.raises(ValueError) as problem:
        read_file_text("cv.doc", b"anything")
    assert "antiword" in str(problem.value) and "Docker" in str(problem.value)


def test_wrong_and_damaged_files():
    with pytest.raises(ValueError):
        read_file_text("photo.png", b"x")
    with pytest.raises(ValueError) as problem:
        read_file_text("cv.pdf", b"this is not a real pdf")
    assert "could not be read" in str(problem.value)


# ---------- the quality check ----------

def test_weak_text_is_noticed():
    full = "Backend developer with experience in Python and databases. " * 12
    assert text_problem(full) == ""
    assert "No text" in text_problem("")
    assert "Only 3 words" in text_problem("Rahim Uddin CV")
    assert "garbled" in text_problem("(cid:12)(cid:44) " + full)
    assert "garbled" in text_problem("#$%& 1234 ^^^ " * 40)
    assert "almost no text" in text_problem(full, pages=4)                   # 4 pages, words for one


# ---------- read_cv: plain code only, when a CV is saved ----------

def test_a_good_docx_is_read_by_code():
    reading = read_cv("cv.docx", sample("karima_tables.docx"))
    assert (reading.source, reading.problem) == ("file", "") and "Karima Akter" in reading.text


def test_saving_a_scanned_pdf_asks_no_ai(monkeypatch):
    """Upload and fetch never call the AI. The screening workflow reads the scanned PDF later (ocr_once)."""
    monkeypatch.setattr("app.ai.llm_client.llm_read_pdf", lambda *a: pytest.fail("the AI must not be asked here"))
    reading = read_cv("scan.pdf", sample("scanned_blank.pdf"))
    assert reading.source == "" and "No text was found" in reading.problem and "Screening will let the AI" in reading.problem


def test_a_weak_docx_is_kept_with_a_problem(tmp_path):
    from docx import Document
    document = Document()
    document.add_paragraph("Nadia Islam, made-up CV, see the picture")
    document.save(tmp_path / "short.docx")
    reading = read_cv("short.docx", (tmp_path / "short.docx").read_bytes())
    assert reading.text and "may be incomplete" in reading.problem and "AI" not in reading.problem


def test_english_check():
    assert looks_english("Backend developer with four years of experience in Python and the cloud.")
    assert not looks_english("নাদিয়া ইসলাম। পাইথন ডেভেলপার, চার বছরের অভিজ্ঞতা।")
    assert not looks_english("Softwareentwickler mit vier Jahren Erfahrung, Python und Datenbanken, Teamarbeit.")


def test_upload_reads_with_code_only(client, make_job):
    job = make_job(approve=True, title="Reader Tester", description="A made-up job for the reading tests.")
    for name, file_name, data in (("Karima Akter", "karima.docx", sample("karima_tables.docx")),
                                  ("Tanvir Hasan", "scan.pdf", sample("scanned_blank.pdf"))):
        client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (file_name, data)}, data={"full_name": name})
    rows = {c["full_name"]: c for c in client.get(f"/api/jobs/{job['id']}/candidates").json()}
    assert rows["Karima Akter"]["text_source"] == "file" and rows["Karima Akter"]["status"] == "new"
    assert rows["Tanvir Hasan"]["text_source"] == "" and rows["Tanvir Hasan"]["status"] == "needs_review"
