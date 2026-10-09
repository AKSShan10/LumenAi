"""Company documents (interviewer only). The AI looks them up before it writes a job (RAG).
Read and delete only: documents are added in the chat (typed, or as an attached file).

  GET    /api/company-documents                    list the documents
  DELETE /api/company-documents/{document_id}      remove one
  GET    /api/company-documents/search?q=...       try the search: which documents would the AI get?
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.job_library.models import CompanyDocument
from app.features.job_library.schemas import DocumentHit, DocumentOut
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_EXAMPLES, TOP_POLICIES, document_out, find_documents)

router = APIRouter(prefix="/api/company-documents", tags=["Company documents"],
                   dependencies=[Depends(require_interviewer)])


@router.get("", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_session)):
    rows = session.exec(select(CompanyDocument).order_by(CompanyDocument.id.desc())).all()
    return [document_out(row) for row in rows]


@router.get("/search", response_model=list[DocumentHit])
def try_search(q: str, session: Session = Depends(get_session)):
    """The same search the job description workflow runs, so the interviewer can see what the AI gets."""
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
