"""Company documents: past job descriptions and policy notes that the AI looks up (RAG)."""
PAST_JOB = ("Backend Developer. You will build REST APIs with Python and FastAPI, write tests and work with "
            "PostgreSQL. We value clear code reviews and steady releases.")
POLICY = ("Hiring policy. Every job description ends with our equal opportunity statement and names the working "
          "model: hybrid, three office days per week.")
OTHER_JOB = ("Graphic Designer. You will design brochures, banners and social media pictures with Figma and "
             "Illustrator for the marketing team.")


def add(client, kind, title, text) -> dict:
    response = client.post("/api/company-documents", json={"kind": kind, "title": title, "text": text})
    assert response.status_code == 201
    return response.json()


def test_add_list_and_remove(client):
    document = add(client, "job_description", "Backend Developer 2025", PAST_JOB)
    assert document["kind"] == "job_description" and document["source"] == "added" and document["words"] > 10
    assert document["id"] in [d["id"] for d in client.get("/api/company-documents").json()]
    assert client.delete(f"/api/company-documents/{document['id']}").status_code == 204
    assert client.delete(f"/api/company-documents/{document['id']}").status_code == 404


def test_bad_documents_are_rejected(client):
    assert client.post("/api/company-documents", json={"kind": "policy", "title": "x", "text": POLICY}).status_code == 422
    assert client.post("/api/company-documents", json={"kind": "policy", "title": "No text", "text": ""}).status_code == 422
    assert client.post("/api/company-documents", json={"kind": "novel", "title": "Wrong kind", "text": POLICY}).status_code == 422


def test_search_finds_the_similar_job_and_the_policy(client):
    backend = add(client, "job_description", "Backend Developer 2025", PAST_JOB)
    designer = add(client, "job_description", "Graphic Designer 2024", OTHER_JOB)
    policy = add(client, "policy", "Hiring policy", POLICY)

    hits = client.get("/api/company-documents/search", params={"q": "Python FastAPI developer for REST APIs"}).json()
    jobs = [h for h in hits if h["kind"] == "job_description"]
    assert jobs[0]["id"] == backend["id"]                              # the most similar past job comes first
    assert policy["id"] in [h["id"] for h in hits if h["kind"] == "policy"]   # policy applies to every job
    for document in (backend, designer, policy):
        client.delete(f"/api/company-documents/{document['id']}")


def test_search_without_embeddings_compares_words(client, monkeypatch):
    from app.features.job_library.services import company_document_service
    monkeypatch.setattr(company_document_service, "embed_texts", lambda texts: None)   # the embedding service is down
    document = add(client, "job_description", "Backend Developer words only", PAST_JOB)
    hits = client.get("/api/company-documents/search", params={"q": "FastAPI PostgreSQL tests"}).json()
    assert document["id"] in [h["id"] for h in hits]
    client.delete(f"/api/company-documents/{document['id']}")


def test_documents_need_login(anonymous):
    assert anonymous.get("/api/company-documents").status_code == 401


# ---------- file upload ----------
def upload(client, filename, data, title=""):
    return client.post("/api/company-documents/upload", data={"kind": "job_description", "title": title},
                       files={"file": (filename, data)})


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


def test_upload_text_word_and_pdf_files(client):
    for filename, data in (("backend-developer.txt", PAST_JOB.encode()),
                           ("backend-developer.docx", docx_bytes(PAST_JOB)),
                           ("backend-developer.pdf", pdf_bytes("Backend Developer with Python and FastAPI"))):
        response = upload(client, filename, data)
        assert response.status_code == 201, filename
        document = response.json()
        assert document["title"] == "backend-developer" and document["words"] >= 5     # title = the file name
        client.delete(f"/api/company-documents/{document['id']}")


def test_uploaded_file_is_found_by_the_search(client):
    document = upload(client, "old-job.docx", docx_bytes(PAST_JOB), title="Backend Developer 2025").json()
    assert document["title"] == "Backend Developer 2025"
    hits = client.get("/api/company-documents/search", params={"q": "Python FastAPI REST APIs"}).json()
    assert document["id"] in [h["id"] for h in hits]
    client.delete(f"/api/company-documents/{document['id']}")


def test_bad_files_are_rejected(client):
    assert upload(client, "photo.png", b"not a document").status_code == 400          # wrong type
    assert upload(client, "empty.txt", b"   ").status_code == 400                     # no text inside
    assert upload(client, "broken.pdf", b"this is not a real pdf").status_code == 400  # cannot be read
    assert upload(client, "big.txt", b"a" * (5 * 1024 * 1024 + 1)).status_code == 400  # too large


def test_upload_needs_login(anonymous):
    assert anonymous.post("/api/company-documents/upload", files={"file": ("a.txt", b"hello")}).status_code == 401
