"""Company documents (RAG).

    add_document()            save a document with its embedding
    find_documents()          the most similar documents of one kind for a text (given to the AI)
    has_document_for_job()    was this approved job already added?
    document_out()            the list row shown on the Job Requirements page

How the search works: every document is stored with an "embedding" (a list of numbers that stands for
its meaning). The search text gets an embedding too, and the documents whose numbers are closest win.
If no embedding is available, the search counts shared words instead.
"""
from sqlmodel import Session, select

from app.ai.llm_client import embed_texts
from app.features.job_library.models import CompanyDocument
from app.features.job_library.schemas import DocumentOut
from app.utils.search_utils import cosine, word_overlap

MAX_WORDS = 400                  # long documents are cut before they go to the AI

# How many documents the AI gets for one job
TOP_EXAMPLES = 2                 # the most similar past job descriptions
MIN_EXAMPLE_SIMILARITY = 0.05    # a past job less similar than this is left out
TOP_POLICIES = 3                 # company policy notes


def add_document(session: Session, title: str, text: str, kind: str = "job_description",
                 source: str = "added", job_id: int | None = None) -> CompanyDocument:
    vector = (embed_texts([f"{title}\n{text}"]) or [None])[0]
    document = CompanyDocument(kind=kind, title=title.strip(), text=text.strip(), source=source,
                               job_id=job_id, embedding=vector)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def find_documents(session: Session, query: str, kind: str, top_k: int, min_similarity: float = 0.0) -> list[dict]:
    rows = session.exec(select(CompanyDocument).where(CompanyDocument.kind == kind)).all()
    if not rows or not query.strip():
        return []
    query_vector = (embed_texts([query]) or [None])[0]
    hits = []
    for row in rows:
        if query_vector and row.embedding:
            similarity = cosine(query_vector, row.embedding)
        else:
            similarity = word_overlap(query, f"{row.title} {row.text}")
        if similarity >= min_similarity:
            hits.append({"id": row.id, "kind": row.kind, "title": row.title, "similarity": round(similarity, 3),
                         "text": " ".join(row.text.split()[:MAX_WORDS])})
    hits.sort(key=lambda hit: hit["similarity"], reverse=True)
    return hits[:top_k]


def has_document_for_job(session: Session, job_id: int) -> bool:
    return session.exec(select(CompanyDocument).where(CompanyDocument.job_id == job_id,
                                                      CompanyDocument.source == "approved job")).first() is not None


def document_out(row: CompanyDocument) -> DocumentOut:
    return DocumentOut(id=row.id, kind=row.kind, title=row.title, source=row.source, job_id=row.job_id,
                       words=len(row.text.split()), created_at=row.created_at)
