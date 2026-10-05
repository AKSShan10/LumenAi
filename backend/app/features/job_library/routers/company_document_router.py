"""Company documents (interviewer only). The AI will look them up before it writes a job (RAG).

  GET    /api/company-documents                    list the documents
  POST   /api/company-documents                    add one as pasted text (a past job description or a policy note)
  POST   /api/company-documents/upload             add one as a file (PDF, DOCX or TXT)
  DELETE /api/company-documents/{document_id}      remove one
  GET    /api/company-documents/search?q=...       try the search: which documents would the AI get?
"""
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.job_library.models import CompanyDocument
from app.features.job_library.schemas import DocumentHit, DocumentIn, DocumentOut, Kind
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_EXAMPLES, TOP_POLICIES, add_document, document_out, find_documents)
from app.utils.file_text_utils import text_from_file

router = APIRouter(prefix="/api/company-documents", tags=["Company documents"],
                   dependencies=[Depends(require_interviewer)])


@router.get("", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_session)):
    rows = session.exec(select(CompanyDocument).order_by(CompanyDocument.id.desc())).all()
    return [document_out(row) for row in rows]


@router.post("", response_model=DocumentOut, status_code=201)
def add(body: DocumentIn, session: Session = Depends(get_session)):
    return document_out(add_document(session, body.title, body.text, kind=body.kind))


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload(file: UploadFile = File(...), kind: Kind = Form("job_description"), title: str = Form(""),
           session: Session = Depends(get_session)):
    """Reads the text out of the file and saves it like a pasted document. The file itself is not kept."""
    filename = file.filename or ""
    try:
        text = text_from_file(filename, file.file.read())
    except ValueError as problem:
        raise HTTPException(400, str(problem))
    title = title.strip() or os.path.splitext(filename)[0]      # no title given -> the file name
    return document_out(add_document(session, title[:120], text[:20000], kind=kind))


@router.get("/search", response_model=list[DocumentHit])
def try_search(q: str, session: Session = Depends(get_session)):
    """The search the AI will use, so the interviewer can see which documents it would get."""
    hits = (find_documents(session, q, "job_description", TOP_EXAMPLES, MIN_EXAMPLE_SIMILARITY)
            + find_documents(session, q, "policy", TOP_POLICIES))
    return [DocumentHit(**{key: hit[key] for key in ("id", "kind", "title", "similarity")}) for hit in hits]


@router.delete("/{document_id}", status_code=204)
def remove(document_id: int, session: Session = Depends(get_session)):
    row = session.get(CompanyDocument, document_id)
    if not row:
        raise HTTPException(404, "Document not found")
    session.delete(row)
    session.commit()
