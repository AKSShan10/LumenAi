"""The assistant chat.

    send_message()      saves the interviewer's message, runs the agent, saves its answer
    confirm_action()    the interviewer said Yes or No to an approval or a job post
    chat_out()          one chat (the current one or an earlier one), the waiting questions and the list of chats
    new_chat()          starts a new chat; the earlier ones are kept in the database
    continue_chat()     makes an earlier chat the current one again

The AI chooses the tools (app/graphs/assistant_agent.py). Approving a job and posting it are
done by backend code, and only after the interviewer clicked Yes: approving here, posting through the posting
workflow (app/graphs/job_post_graph.py), which pauses until the interviewer answers.
"""
import logging
import time
import uuid

from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.assistant.models import AssistantAction, ChatConversation, ChatMessage
from app.features.assistant.schemas import ActionOut, ChatOut, ChatSummary, MessageOut
from app.features.jobs.models import Job
from app.features.jobs.services.job_service import approve_job
from app.features.system.models import WorkflowRun
from app.graphs.assistant_agent import run_assistant
from app.graphs.job_post_graph import answer_post, start_post
from app.utils.datetime_utils import utc_now

log = logging.getLogger("assistant")

HISTORY = 12                     # how many earlier lines start a new thread (a chat without LangGraph memory yet)
NEWEST_FIRST = (ChatConversation.opened_at.desc(), ChatConversation.id.desc())    # the current chat comes first
TITLE_CHARS = 60                 # how much of the first message is shown in the list of chats
PREVIEW_CHARS = 600              # how much of an attached file the AI sees (the tool stores the whole text)


def _for_ai(message: ChatMessage) -> dict:
    content = message.content
    if message.attachment_text:                       # the AI gets a note, not the whole file
        words = len(message.attachment_text.split())
        content += (f"\n[Attached file: {message.attachment_name}, message_id={message.id}, {words} words. "
                    f"It begins: {message.attachment_text[:PREVIEW_CHARS]}]")
    return {"role": message.role, "content": content}


def current_conversation(session: Session) -> ChatConversation:
    """The chat that is open now: the one that was opened last. The very first call creates it."""
    conversation = session.exec(select(ChatConversation).order_by(*NEWEST_FIRST)).first()
    if not conversation:
        conversation = ChatConversation()
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    return conversation


def _messages(session: Session, conversation_id: int) -> list[ChatMessage]:
    return session.exec(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                        .order_by(ChatMessage.id)).all()


def _chat_list(session: Session) -> list[ChatSummary]:
    """All chats, the current one first. The title is the first thing the interviewer wrote in it."""
    chats = []
    for conversation in session.exec(select(ChatConversation).order_by(*NEWEST_FIRST)).all():
        messages = _messages(session, conversation.id)
        first = next((m.content for m in messages if m.role == "user"), "")
        chats.append(ChatSummary(id=conversation.id, title=first[:TITLE_CHARS] or "New chat",
                                 started_at=conversation.created_at, messages=len(messages)))
    return chats


def chat_out(session: Session, chat_id: int | None = None) -> ChatOut:
    """The current chat, or an earlier one when chat_id is given (an earlier chat is only read here)."""
    current = current_conversation(session)
    if chat_id is not None and not session.get(ChatConversation, chat_id):
        raise HTTPException(404, "That chat was not found")
    shown = current.id if chat_id is None else chat_id
    waiting = []
    if shown == current.id:
        waiting = session.exec(select(AssistantAction).where(AssistantAction.status == "pending")
                               .order_by(AssistantAction.id)).all()
    return ChatOut(chat_id=shown, is_current=shown == current.id,
                   messages=[MessageOut(**m.model_dump()) for m in _messages(session, shown)],
                   actions=[ActionOut(**a.model_dump()) for a in waiting],
                   chats=_chat_list(session))


def _new_lines_for_ai(session: Session, conversation: ChatConversation) -> list[ChatMessage]:
    """The chat lines the agent's thread does not have yet: the interviewer's new message, and the results of
    Yes / No answers given since the last message. A chat without a thread yet (a new chat, or one from before
    the memory existed) starts its thread with its last HISTORY lines."""
    lines = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
    if conversation.agent_thread and conversation.agent_seen_id:
        return session.exec(lines.where(ChatMessage.id > conversation.agent_seen_id).order_by(ChatMessage.id)).all()
    recent = session.exec(lines.order_by(ChatMessage.id.desc()).limit(HISTORY)).all()
    return list(reversed(recent))


def send_message(session: Session, text: str, attachment_name: str = "", attachment_text: str = "") -> ChatOut:
    conversation = current_conversation(session)
    session.add(ChatMessage(conversation_id=conversation.id, role="user", content=text.strip(),
                            attachment_name=attachment_name, attachment_text=attachment_text))
    if not conversation.agent_thread:                 # this chat's thread in LangGraph's checkpointer
        conversation.agent_thread = f"chat-{conversation.id}-{uuid.uuid4().hex[:8]}"
    session.add(conversation)
    session.commit()
    # the AI only gets lines of this chat, so an earlier chat cannot confuse it; earlier lines are in its thread
    new_lines = _new_lines_for_ai(session, conversation)

    last_question = session.exec(select(AssistantAction.id).order_by(AssistantAction.id.desc())).first() or 0
    started = time.time()
    result = run_assistant([_for_ai(message) for message in new_lines], conversation.agent_thread)
    seconds = round(time.time() - started, 2)
    _start_posting_runs(session, last_question)

    answer = result["answer"] or "I have no answer for that."
    if result["error"]:
        answer = "The assistant could not answer: " + result["error"] + "."
    reply = ChatMessage(conversation_id=conversation.id, role="assistant", content=answer, tools=result["tools"])
    session.add(reply)
    session.add(WorkflowRun(stage="assistant", subject_id=0, outcome="failed" if result["error"] else "done",
                            error=result["error"], seconds=seconds))
    session.commit()
    if result["error"]:
        # a run that stopped half way can leave the thread unfinished: the next message starts a fresh thread
        # from the last lines of the chat
        conversation.agent_thread, conversation.agent_seen_id = "", 0
    else:
        conversation.agent_seen_id = reply.id         # the thread has everything up to this answer
    session.add(conversation)
    session.commit()
    log.info("assistant %s tools=%s %.1fs", "failed" if result["error"] else "ok", ",".join(result["tools"]) or "-", seconds)
    return chat_out(session)


def _start_posting_runs(session: Session, after_id: int) -> None:
    """Each new "post this job?" question the AI asked gets its posting workflow, which pauses at once for the
    interviewer's answer (graphs/job_post_graph.py). Started here, after the AI's turn, not inside the AI's tool."""
    asked = session.exec(select(AssistantAction).where(AssistantAction.id > after_id, AssistantAction.kind == "post_job",
                                                       AssistantAction.status == "pending")).all()
    for action in asked:
        start_post(action)
    session.expire_all()                              # the workflow may have saved a problem on a question


def confirm_action(session: Session, action_id: int, yes: bool) -> ChatOut:
    action = session.get(AssistantAction, action_id)
    if not action:
        raise HTTPException(404, "That question was not found")
    if action.status != "pending":
        raise HTTPException(400, "That question was already answered")

    if action.kind == "post_job":                     # the posting workflow continues with the answer
        answer_post(action, yes)
        session.refresh(action)
    elif not yes:
        action.status, action.result = "cancelled", "You said No. Nothing was changed."
    else:
        try:
            job = session.get(Job, action.job_id)
            if not job:
                raise HTTPException(404, "The job no longer exists")
            approve_job(session, job, add_to_library=True)
            action.status, action.result = "done", f"The job \"{job.title}\" is approved."
        except HTTPException as problem:              # for example: the job was edited and is a draft again
            action.status, action.result = "failed", str(problem.detail)
    session.add(action)
    session.add(ChatMessage(conversation_id=current_conversation(session).id, role="assistant",
                            content=action.result))                 # so the AI and the screen both know
    session.commit()
    log.info("assistant action=%s job=%s %s", action.kind, action.job_id, action.status)
    return chat_out(session)


def _cancel_waiting_questions(session: Session) -> None:
    """A question that still waits for a Yes or No belongs to the chat that is being left."""
    for action in session.exec(select(AssistantAction).where(AssistantAction.status == "pending")).all():
        action.status, action.result = "cancelled", "Another chat was opened before this was answered."
        session.add(action)


def new_chat(session: Session) -> ChatOut:
    """Starts a new chat. Nothing is deleted: the earlier chats stay in the database."""
    if _messages(session, current_conversation(session).id):          # an empty chat is simply used again
        session.add(ChatConversation())
    _cancel_waiting_questions(session)
    session.commit()
    return chat_out(session)


def continue_chat(session: Session, chat_id: int) -> ChatOut:
    """Makes an earlier chat the current one again, so the interviewer can go on writing in it.
    The AI is then given the last lines of that chat. The chat that is left stays in the database."""
    chosen = session.get(ChatConversation, chat_id)
    if not chosen:
        raise HTTPException(404, "That chat was not found")
    current = current_conversation(session)
    if chosen.id != current.id:
        if not _messages(session, current.id):                        # do not keep an empty chat in the list
            session.delete(current)
        _cancel_waiting_questions(session)
        chosen.opened_at = utc_now()
        session.add(chosen)
        session.commit()
    return chat_out(session)
