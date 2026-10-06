"""The assistant chat (interviewer only).

  GET    /api/assistant/chat                    the conversation and the questions waiting for Yes / No
  POST   /api/assistant/chat                    send a message, with an optional file (PDF, DOCX or TXT)
  POST   /api/assistant/actions/{action_id}     answer Yes or No to an approval or a Telegram post
  DELETE /api/assistant/chat                    start a new conversation
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.assistant.schemas import ChatOut, ConfirmIn
from app.features.assistant.services.assistant_service import chat_out, clear_chat, confirm_action, send_message
from app.utils.file_text_utils import text_from_file

router = APIRouter(prefix="/api/assistant", tags=["Assistant"], dependencies=[Depends(require_interviewer)])
MAX_MESSAGE_CHARS = 4000


@router.get("/chat", response_model=ChatOut)
def get_chat(session: Session = Depends(get_session)):
    return chat_out(session)


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


@router.post("/actions/{action_id}", response_model=ChatOut)
def answer_question(action_id: int, body: ConfirmIn, session: Session = Depends(get_session)):
    return confirm_action(session, action_id, body.yes)


@router.delete("/chat", response_model=ChatOut)
def new_chat(session: Session = Depends(get_session)):
    return clear_chat(session)
