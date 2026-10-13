"""The recruitment MCP server: the tools the assistant can choose from.

    list_company_documents()                       the company documents that are stored
    search_company_documents(query)                the documents closest in meaning to a text (RAG)
    add_company_document(kind, title, text)        store a text as a company document
    save_attached_file_as_document(message_id..)   store the file that was attached to a chat message
    write_job_draft(prompt, ...)                   run the job description workflow (nothing is saved)
    save_job(...)                                  save a job as a draft, or change a saved job
    list_jobs() / get_job(job_id)                  the saved jobs
    prepare_job_post(job_id)                  the post made from an approved job

Started by the assistant:   python -m app.mcp_servers.recruitment_server      (stdio transport)
Every tool answers with JSON. A problem is returned as {"error": "..."} in plain words.

There is NO tool here that approves a job or posts it. Those two need a person's Yes
(see app/graphs/assistant_agent.py).
"""
import json

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import all_models  # noqa: F401  (registers every table)
from app.core.database import engine
from app.features.assistant.models import ChatMessage
from app.features.job_library.models import CompanyDocument
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_EXAMPLES, TOP_POLICIES, add_document, find_documents)
from app.features.jobs.models import Job
from app.features.jobs.schemas import JobCreate
from app.features.jobs.services.job_posting_service import approved_post
from app.features.jobs.services.job_service import create_job, update_job
from app.graphs.job_description_graph import write_job_draft as run_job_description_workflow

server = FastMCP("lumenai-recruitment")
KINDS = ("job_description", "policy")


# Turns a tool's result into a JSON string (every MCP tool here answers with JSON)
def _answer(data) -> str:
    return json.dumps(data, default=str)


# Turns a Job row into a dict with its main fields, for a tool's JSON answer
def _job(job: Job) -> dict:
    return {"id": job.id, "title": job.title, "status": job.status, "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills, "min_years": job.min_years,
            "qualifications": job.qualifications, "description": job.description}


# ---------- company documents ----------

@server.tool()
def list_company_documents() -> str:
    """List the stored company documents (past job descriptions and policy notes). Returns JSON."""
    with Session(engine) as session:
        rows = session.exec(select(CompanyDocument).order_by(CompanyDocument.id.desc())).all()
        return _answer({"documents": [{"id": r.id, "kind": r.kind, "title": r.title, "words": len(r.text.split())}
                                      for r in rows]})


@server.tool()
def search_company_documents(query: str) -> str:
    """Find the company documents closest in meaning to the query. Returns JSON with titles and similarity (0 to 1)."""
    with Session(engine) as session:
        hits = (find_documents(session, query, "job_description", TOP_EXAMPLES, MIN_EXAMPLE_SIMILARITY)
                + find_documents(session, query, "policy", TOP_POLICIES))
        return _answer({"documents": [{"id": h["id"], "kind": h["kind"], "title": h["title"],
                                       "similarity": h["similarity"]} for h in hits]})


@server.tool()
def add_company_document(kind: str, title: str, text: str) -> str:
    """Store a text as a company document. kind is "job_description" (a past job description) or "policy"."""
    if kind not in KINDS:
        return _answer({"error": 'kind must be "job_description" or "policy"'})
    if len(title.strip()) < 2 or not text.strip():
        return _answer({"error": "a title and a text are needed"})
    with Session(engine) as session:
        document = add_document(session, title[:120], text[:20000], kind=kind)
        return _answer({"saved": True, "id": document.id, "kind": kind, "title": document.title,
                        "words": len(document.text.split())})


@server.tool()
def save_attached_file_as_document(message_id: int, kind: str, title: str = "") -> str:
    """Store the file attached to a chat message as a company document. The whole text of the file is stored
    exactly as it was read. kind is "job_description" or "policy". An empty title means the file name is used."""
    if kind not in KINDS:
        return _answer({"error": 'kind must be "job_description" or "policy"'})
    with Session(engine) as session:
        message = session.get(ChatMessage, message_id)
        if not message or not message.attachment_text:
            return _answer({"error": "that message has no attached file"})
        name = title.strip() or message.attachment_name.rsplit(".", 1)[0]
        document = add_document(session, name[:120], message.attachment_text[:20000], kind=kind)
        return _answer({"saved": True, "id": document.id, "kind": kind, "title": document.title,
                        "words": len(document.text.split())})


# ---------- jobs ----------

@server.tool()
def write_job_draft(prompt: str, change_request: str = "", previous_description: str = "") -> str:
    """Write a job profile and description from a short prompt, using the company documents (RAG).
    Nothing is saved. To improve an earlier draft, also give change_request and previous_description.
    Returns JSON: the draft, the documents that were followed, and problems a check still found."""
    result = run_job_description_workflow(prompt, change_request, previous_description)
    if result["error"]:
        return _answer({"error": "the job could not be written: " + result["error"]})
    return _answer({"draft": result["draft"], "followed_examples": [e["title"] for e in result["examples"]],
                    "followed_policies": [p["title"] for p in result["policies"]], "problems": result["problems"]})


@server.tool()
def save_job(title: str, description: str, required_skills: list[str], preferred_skills: list[str] | None = None,
             min_years: int = 0, qualifications: str = "", prompt: str = "", job_id: int = 0) -> str:
    """Save a job as a draft. Give job_id to change a job that is already saved (it becomes a draft again)."""
    try:
        body = JobCreate(title=title, description=description, required_skills=required_skills,
                         preferred_skills=preferred_skills or [], min_years=min_years,
                         qualifications=qualifications, prompt=prompt)
    except ValidationError as problem:
        return _answer({"error": "the job cannot be saved: " + "; ".join(e["msg"] for e in problem.errors())})
    with Session(engine) as session:
        if job_id:
            job = session.get(Job, job_id)
            if not job:
                return _answer({"error": f"job {job_id} was not found"})
            job = update_job(session, job, body)
        else:
            job = create_job(session, body)
        return _answer({"saved": True, "job": _job(job)})


@server.tool()
def list_jobs() -> str:
    """List the saved jobs, newest first. Returns JSON with id, title and status (draft or approved)."""
    with Session(engine) as session:
        rows = session.exec(select(Job).order_by(Job.id.desc())).all()
        return _answer({"jobs": [{"id": r.id, "title": r.title, "status": r.status} for r in rows]})


@server.tool()
def get_job(job_id: int) -> str:
    """One saved job with all its fields."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        return _answer({"job": _job(job)} if job else {"error": f"job {job_id} was not found"})


@server.tool()
def prepare_job_post(job_id: int) -> str:
    """The post for an approved job, made from the approved description. Nothing is posted."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return _answer({"error": f"job {job_id} was not found"})
        try:
            return _answer({"job_id": job.id, "text": approved_post(job)})
        except HTTPException as problem:
            return _answer({"error": str(problem.detail)})


if __name__ == "__main__":
    server.run()          # stdio transport
