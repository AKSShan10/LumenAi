"""The assistant chat.

    send_message()      saves the interviewer's message, runs the agent, saves its answer
    confirm_action()    the interviewer said Yes or No to an approval or a Telegram post
    chat_out()          the conversation and the questions that still wait for an answer

The AI chooses the tools (app/graphs/assistant_agent.py). Approving a job and posting to Telegram are
done here, by backend code, and only after the interviewer clicked Yes.
"""
import logging
import time

from fastapi import HTTPException
from sqlmodel import Session, delete, select

from app.features.assistant.models import AssistantAction, ChatMessage
from app.features.assistant.schemas import ActionOut, ChatOut, MessageOut
from app.features.jobs.models import Job
from app.features.jobs.services.job_posting_service import post_job
from app.features.jobs.services.job_service import approve_job
from app.features.system.models import WorkflowRun
from app.graphs.assistant_agent import run_assistant

log = logging.getLogger("assistant")

HISTORY = 12                     # how many earlier messages the AI is given
PREVIEW_CHARS = 600              # how much of an attached file the AI sees (the tool stores the whole text)


def _for_ai(message: ChatMessage) -> dict:
    content = message.content
    if message.attachment_text:                       # the AI gets a note, not the whole file
        words = len(message.attachment_text.split())
        content += (f"\n[Attached file: {message.attachment_name}, message_id={message.id}, {words} words. "
                    f"It begins: {message.attachment_text[:PREVIEW_CHARS]}]")
    return {"role": message.role, "content": content}


def chat_out(session: Session) -> ChatOut:
    messages = session.exec(select(ChatMessage).order_by(ChatMessage.id)).all()
    waiting = session.exec(select(AssistantAction).where(AssistantAction.status == "pending")
                           .order_by(AssistantAction.id)).all()
    return ChatOut(messages=[MessageOut(**m.model_dump()) for m in messages],
                   actions=[ActionOut(**a.model_dump()) for a in waiting])


def send_message(session: Session, text: str, attachment_name: str = "", attachment_text: str = "") -> ChatOut:
    session.add(ChatMessage(role="user", content=text.strip(), attachment_name=attachment_name,
                            attachment_text=attachment_text))
    session.commit()
    recent = session.exec(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(HISTORY)).all()

    started = time.time()
    result = run_assistant([_for_ai(message) for message in reversed(recent)])
    seconds = round(time.time() - started, 2)

    answer = result["answer"] or "I have no answer for that."
    if result["error"]:
        answer = "The assistant could not answer: " + result["error"] + "."
    session.add(ChatMessage(role="assistant", content=answer, tools=result["tools"]))
    session.add(WorkflowRun(stage="assistant", subject_id=0, outcome="failed" if result["error"] else "done",
                            error=result["error"], seconds=seconds))
    session.commit()
    log.info("assistant %s tools=%s %.1fs", "failed" if result["error"] else "ok", ",".join(result["tools"]) or "-", seconds)
    return chat_out(session)


def confirm_action(session: Session, action_id: int, yes: bool) -> ChatOut:
    action = session.get(AssistantAction, action_id)
    if not action:
        raise HTTPException(404, "That question was not found")
    if action.status != "pending":
        raise HTTPException(400, "That question was already answered")

    if not yes:
        action.status, action.result = "cancelled", "You said No. Nothing was changed."
    else:
        try:
            job = session.get(Job, action.job_id)
            if not job:
                raise HTTPException(404, "The job no longer exists")
            if action.kind == "approve_job":
                approve_job(session, job, add_to_library=True)
                action.status, action.result = "done", f"The job \"{job.title}\" is approved."
            else:
                posting = post_job(session, job, action.text, action.apply_url)
                if posting.status == "posted":
                    action.status, action.result = "done", f"The job \"{job.title}\" was posted to the Telegram channel."
                else:
                    action.status, action.result = "failed", "Telegram did not accept the post: " + posting.error
        except HTTPException as problem:              # for example: the job was edited and is a draft again
            action.status, action.result = "failed", str(problem.detail)
    session.add(action)
    session.add(ChatMessage(role="assistant", content=action.result))    # so the AI and the screen both know
    session.commit()
    log.info("assistant action=%s job=%s %s", action.kind, action.job_id, action.status)
    return chat_out(session)


def clear_chat(session: Session) -> ChatOut:
    """Starts a new conversation. Saved documents, jobs and posts are not touched."""
    session.exec(delete(ChatMessage))
    session.exec(delete(AssistantAction).where(AssistantAction.status == "pending"))
    session.commit()
    return chat_out(session)
