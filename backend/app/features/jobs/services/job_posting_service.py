"""Posting an approved job to the company blog (Blogger).

    approved_post()    the post made by code from the approved job: the words the interviewer already approved
    post_job()         the backend calls the Blogger MCP tool and saves how it ended
    posting_check()    is Blogger set up? (used by the Settings page)

A post is sent only after the interviewer answered Yes in the chat. The backend code calls the tool;
the AI never chooses or calls it.
"""
import json
import logging

from fastapi import HTTPException
from sqlmodel import Session

from app.features.jobs.models import Job, JobPosting
from app.mcp_servers.client import McpError, call_tool

log = logging.getLogger("job_posting")

BLOGGER_SERVER = "app.mcp_servers.blogger_server"
CHANNEL = "blogger"                                  # saved with every post
BUTTON_TEXT = "Apply now"


def must_be_approved(job: Job) -> None:
    if job.status != "approved":
        raise HTTPException(400, "Approve the job first. Only an approved job can be posted.")


def approved_post(job: Job) -> str:
    """No AI here: the title, the approved description and the requirements, put together by code."""
    must_be_approved(job)
    lines = [job.title, "", job.description.strip(), "", "Required skills: " + ", ".join(job.required_skills)]
    if job.preferred_skills:
        lines.append("Nice to have: " + ", ".join(job.preferred_skills))
    if job.min_years:
        lines.append(f"Experience: {job.min_years}+ years")
    if job.qualifications:
        lines.append("Qualifications: " + job.qualifications)
    return "\n".join(lines)


def _send(job: Job, text: str, apply_url: str) -> dict:
    """Calls the Blogger MCP tool. Returns {"ok", "link", "error"}.
    The job title is the title of the blog post; the link becomes "Apply now" under the text, added by code."""
    return json.loads(call_tool(BLOGGER_SERVER, "publish_blog_post",
                                {"title": job.title, "text": text.strip(),
                                 "button_text": BUTTON_TEXT, "button_url": apply_url}))


def post_job(session: Session, job: Job, text: str, apply_url: str) -> JobPosting:
    must_be_approved(job)
    posting = JobPosting(job_id=job.id, channel=CHANNEL, text=text.strip(), apply_url=apply_url)
    try:
        answer = _send(job, text, apply_url)
    except (McpError, ValueError) as problem:
        answer = {"ok": False, "error": f"The posting tool did not answer ({problem})"}

    if answer.get("ok"):
        posting.message_link = answer.get("link") or ""
    else:
        posting.status, posting.error = "failed", answer.get("error") or "unknown error"
    log.info("%s post job=%s %s%s", posting.channel, job.id, posting.status, f" ({posting.error})" if posting.error else "")
    session.add(posting)              # failed tries are saved too, so the interviewer sees what went wrong
    session.commit()
    session.refresh(posting)
    return posting


def posting_check() -> dict:
    """Is Blogger set up? Posts nothing. Used by the Settings page."""
    try:
        return json.loads(call_tool(BLOGGER_SERVER, "check_blogger_settings"))
    except (McpError, ValueError) as problem:
        return {"ok": False, "message": f"The Blogger tool did not answer ({problem})"}
