"""The assistant chat (interviewer only).

  GET    /api/assistant/chat                    the current chat, the questions waiting for Yes / No, the list of chats
  GET    /api/assistant/chat?chat_id=3          read an earlier chat
  POST   /api/assistant/chat/3/continue         make an earlier chat the current one again
  POST   /api/assistant/chat                    send a message, with an optional file (PDF, DOCX or TXT)
  POST   /api/assistant/actions/{action_id}     answer Yes or No to an approval or a job post
  POST   /api/assistant/chat/new                start a new chat (the earlier ones are kept)
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.assistant.schemas import ChatOut, ConfirmIn
from app.features.assistant.services.assistant_service import chat_out, confirm_action, continue_chat, new_chat, send_message
from app.utils.file_text_utils import text_from_file

# → every route here needs a valid interviewer token (require_interviewer)
router = APIRouter(prefix="/api/assistant", tags=["Assistant"], dependencies=[Depends(require_interviewer)])
MAX_MESSAGE_CHARS = 4000


# GET /api/assistant/chat: returns the current or an earlier chat (?chat_id=) and waiting questions (chat_out)
@router.get("/chat", response_model=ChatOut)
def get_chat(chat_id: int | None = None, session: Session = Depends(get_session)):
    return chat_out(session, chat_id)


# POST /api/assistant/chat: checks the text and optional file, then lets the AI agent answer (send_message)
@router.post("/chat", response_model=ChatOut)
def post_message(text: str = Form(""), file: UploadFile | None = File(None), session: Session = Depends(get_session)):
    text = text.strip()
    if len(text) > MAX_MESSAGE_CHARS:
        raise HTTPException(400, "The message is too long (4000 characters at most).")
    name, file_text = "", ""
    if file is not None and file.filename:
        try:
            name, file_text = file.filename, text_from_file(file.filename, file.file.read())[:20000]
        except ValueError as problem:
            raise HTTPException(400, str(problem))
    if not text and not file_text:
        raise HTTPException(400, "Write a message or attach a file.")
    return send_message(session, text or "Please store this file.", name, file_text)


# POST /api/assistant/actions/{action_id}: saves the interviewer's Yes or No to a waiting question (confirm_action)
@router.post("/actions/{action_id}", response_model=ChatOut)
def answer_question(action_id: int, body: ConfirmIn, session: Session = Depends(get_session)):
    return confirm_action(session, action_id, body.yes)


# POST /api/assistant/chat/new: starts a new chat and keeps the earlier ones (new_chat)
@router.post("/chat/new", response_model=ChatOut)
def start_new_chat(session: Session = Depends(get_session)):
    return new_chat(session)


# POST /api/assistant/chat/{chat_id}/continue: makes an earlier chat the current one again (continue_chat)
@router.post("/chat/{chat_id}/continue", response_model=ChatOut)
def continue_earlier_chat(chat_id: int, session: Session = Depends(get_session)):
    return continue_chat(session, chat_id)
