"""Company documents: past job descriptions and policy notes that the AI looks up (RAG)."""
PAST_JOB = ("Backend Developer. You will build REST APIs with Python and FastAPI, write tests and work with "
            "PostgreSQL. We value clear code reviews and steady releases.")
POLICY = ("Hiring policy. Every job description ends with our equal opportunity statement and names the working "
          "model: hybrid, three office days per week.")
OTHER_JOB = ("Graphic Designer. You will design brochures, banners and social media pictures with Figma and "
             "Illustrator for the marketing team.")


def test_add_list_and_remove(client, add_doc):
    document = add_doc("job_description", "Backend Developer 2025", PAST_JOB)
    assert document["kind"] == "job_description" and document["source"] == "added" and document["words"] > 10
    assert document["id"] in [d["id"] for d in client.get("/api/company-documents").json()]
    assert client.delete(f"/api/company-documents/{document['id']}").status_code == 204
    assert client.delete(f"/api/company-documents/{document['id']}").status_code == 404


def test_card_preview_and_the_whole_text(client, add_doc):
    """The Knowledge base card shows the first words; "View" reads the whole text."""
    long_text = POLICY + " " + POLICY                                      # more words than the card shows
    document = add_doc("policy", "Hiring policy", long_text)
    card = next(d for d in client.get("/api/company-documents").json() if d["id"] == document["id"])
    assert card["preview"].startswith("Hiring policy. Every job description") and card["preview"].endswith(" ...")
    assert len(card["preview"].split()) == 31                              # 30 words and the "..."
    whole = client.get(f"/api/company-documents/{document['id']}").json()
    assert whole["text"] == long_text and whole["title"] == "Hiring policy"
    client.delete(f"/api/company-documents/{document['id']}")
    assert client.get(f"/api/company-documents/{document['id']}").status_code == 404


def test_documents_are_only_read_and_removed_through_the_api(client):
    """Documents are added in the chat (typed or as an attached file). The old form endpoints are gone."""
    assert client.post("/api/company-documents", json={"kind": "policy", "title": "Policy", "text": POLICY}).status_code == 405
    assert client.post("/api/company-documents/upload", files={"file": ("a.txt", b"hello")}).status_code == 405


def test_search_finds_the_similar_job_and_the_policy(client, add_doc):
    backend = add_doc("job_description", "Backend Developer 2025", PAST_JOB)
    designer = add_doc("job_description", "Graphic Designer 2024", OTHER_JOB)
    policy = add_doc("policy", "Hiring policy", POLICY)

    hits = client.get("/api/company-documents/search", params={"q": "Python FastAPI developer for REST APIs"}).json()
    jobs = [h for h in hits if h["kind"] == "job_description"]
    assert jobs[0]["id"] == backend["id"]                              # the most similar past job comes first
    assert policy["id"] in [h["id"] for h in hits if h["kind"] == "policy"]   # policy applies to every job
    for document in (backend, designer, policy):
        client.delete(f"/api/company-documents/{document['id']}")


def test_search_without_embeddings_compares_words(client, add_doc, monkeypatch):
    from app.features.job_library.services import company_document_service
    monkeypatch.setattr(company_document_service, "embed_texts", lambda texts: None)   # the embedding service is down
    document = add_doc("job_description", "Backend Developer words only", PAST_JOB)
    hits = client.get("/api/company-documents/search", params={"q": "FastAPI PostgreSQL tests"}).json()
    assert document["id"] in [h["id"] for h in hits]
    client.delete(f"/api/company-documents/{document['id']}")


def test_documents_need_login(anonymous):
    assert anonymous.get("/api/company-documents").status_code == 401


# ---------- reading files (used when a file is attached in the chat) ----------
import pytest  # noqa: E402

from app.utils.file_text_utils import text_from_file  # noqa: E402


def docx_bytes(text) -> bytes:
    import io
    from docx import Document
    document, buffer = Document(), io.BytesIO()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def pdf_bytes(text) -> bytes:
    """A very small one-page PDF with one line of text, built by hand so no extra package is needed."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return pdf + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref


def test_text_is_read_from_text_word_and_pdf_files():
    assert text_from_file("backend-developer.txt", PAST_JOB.encode()) == PAST_JOB
    assert PAST_JOB in text_from_file("backend-developer.docx", docx_bytes(PAST_JOB))
    assert "Backend Developer with Python" in text_from_file("backend-developer.pdf", pdf_bytes("Backend Developer with Python and FastAPI"))


@pytest.mark.parametrize("filename, data", [("photo.png", b"not a document"),                 # wrong type
                                            ("empty.txt", b"   "),                            # no text inside
                                            ("broken.pdf", b"this is not a real pdf"),         # cannot be read
                                            ("big.txt", b"a" * (5 * 1024 * 1024 + 1))])        # too large
def test_bad_files_are_refused_with_a_reason(filename, data):
    with pytest.raises(ValueError):
        text_from_file(filename, data)
