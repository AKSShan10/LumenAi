"""Posting an approved job to the Telegram channel.

    approved_post()    the post made by code from the approved job: the words the interviewer already approved
    draft_post()       optional: the AI writes a shorter post (runs the job post workflow); nothing is saved or posted
    full_message()     the post plus the application link, exactly as it goes to Telegram
    post_job()         the backend calls the Telegram MCP tool and saves how it ended
    telegram_check()   is the bot set up? (used by the Settings page)

A post is sent only when the interviewer clicks "Post to Telegram". The backend code calls the tool;
the AI never chooses or calls it.
"""
import json
import logging

from fastapi import HTTPException
from sqlmodel import Session

from app.features.jobs.models import Job, JobPosting
from app.features.jobs.schemas import PostDraftOut
from app.graphs.job_post_graph import write_job_post
from app.mcp_servers.client import McpError, call_tool

log = logging.getLogger("job_posting")

TELEGRAM_SERVER = "app.mcp_servers.telegram_server"
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


def draft_post(job: Job, change_request: str = "", previous: str = "") -> PostDraftOut:
    must_be_approved(job)
    result = write_job_post(job.model_dump(), change_request, previous)
    if result["error"]:
        return PostDraftOut(from_ai=False, message="The AI could not write the post: " + result["error"])
    message = "Please check: " + "; ".join(result["problems"]) if result["problems"] else ""
    return PostDraftOut(from_ai=True, message=message, text=result["text"])


def full_message(text: str, apply_url: str) -> str:
    """The link is added by code, so it is always the link the interviewer gave."""
    return f"{text.strip()}\n\nApply here: {apply_url}"


def post_job(session: Session, job: Job, text: str, apply_url: str) -> JobPosting:
    must_be_approved(job)
    posting = JobPosting(job_id=job.id, text=text.strip(), apply_url=apply_url)
    try:
        answer = json.loads(call_tool(TELEGRAM_SERVER, "send_channel_post",
                                      {"text": full_message(text, apply_url),
                                       "button_text": BUTTON_TEXT, "button_url": apply_url}))
    except (McpError, ValueError) as problem:
        answer = {"ok": False, "error": f"The Telegram tool did not answer ({problem})"}

    if answer.get("ok"):
        posting.message_id, posting.message_link = answer.get("message_id") or 0, answer.get("link") or ""
    else:
        posting.status, posting.error = "failed", answer.get("error") or "unknown error"
    log.info("telegram post job=%s %s%s", job.id, posting.status, f" ({posting.error})" if posting.error else "")
    session.add(posting)              # failed tries are saved too, so the interviewer sees what went wrong
    session.commit()
    session.refresh(posting)
    return posting


def telegram_check() -> dict:
    try:
        return json.loads(call_tool(TELEGRAM_SERVER, "check_telegram_settings"))
    except (McpError, ValueError) as problem:
        return {"ok": False, "message": f"The Telegram tool did not answer ({problem})"}
