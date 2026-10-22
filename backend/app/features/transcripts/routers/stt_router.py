"""The live transcript: each browser sends its own microphone here, so the speaker is known from the line it uses.

  WS /api/sessions/{id}/stt    the interviewer's microphone. The first message is {"token": "<login token>"}
                               (sent as a message, not in the address, so it never appears in a log)
  WS /api/join/{token}/stt     the candidate's microphone, with the private token of the invitation link

Only while the call is live. After that the browser sends binary messages: 16 kHz, 16-bit mono sound.
The answer for every finished sentence: {"speaker", "text", "start_sec", "end_sec"}; for a sentence the echo guard
dropped: {"speaker", "dropped": true}; when something is wrong: {"error": "plain words"} and the line closes.
The sound is passed to the speech-to-text service and never stored.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import engine
from app.core.security import is_valid_token
from app.features.interviews.models import InterviewSession
from app.features.interviews.routers.join_router import interview_of
from app.features.transcripts.services import stt_service, transcript_service
from app.features.transcripts.services.stt_service import SttError

router = APIRouter(tags=["Live transcript"])
LOGIN_WAIT_SEC = 10


# WS /api/sessions/{id}/stt: the interviewer's microphone (the login token comes in the first message)
@router.websocket("/api/sessions/{session_id}/stt")
async def interviewer_stt(websocket: WebSocket, session_id: int):
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), LOGIN_WAIT_SEC)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError):
        first = {}
    if not isinstance(first, dict) or not is_valid_token(str(first.get("token", ""))):
        return await _stop(websocket, "Please log in again.")
    await _listen(websocket, session_id, "interviewer")


# WS /api/join/{token}/stt: the candidate's microphone, found by the private token of the invitation link
@router.websocket("/api/join/{token}/stt")
async def candidate_stt(websocket: WebSocket, token: str):
    await websocket.accept()
    try:
        with Session(engine) as session:
            session_id = interview_of(session, token).id
    except HTTPException as problem:
        return await _stop(websocket, problem.detail)
    await _listen(websocket, session_id, "candidate")


# Sends one error in plain words and closes the line
async def _stop(websocket: WebSocket, message: str) -> None:
    try:
        await websocket.send_json({"error": message})
        await websocket.close()
    except Exception:                                    # the browser already left
        pass


async def _listen(websocket: WebSocket, session_id: int, speaker: str) -> None:
    """Passes the sound to speech-to-text and saves every finished sentence with its time and speaker."""
    with Session(engine) as session:
        interview = session.get(InterviewSession, session_id)
        if not interview or interview.status != "live":
            return await _stop(websocket, "The transcript starts when the interview is live.")
        offset = transcript_service.seconds_since_start(interview)    # this stream starts now, the interview earlier
    problem = stt_service.stt_problem()
    if problem:
        return await _stop(websocket, problem)

    # Saves one finished sentence (in a worker thread: the database is not async) and tells the browser
    async def on_sentence(text: str, start: float, end: float):
        def save():
            with Session(engine) as db:
                return transcript_service.save_turn(db, session_id, speaker, text, offset + start, offset + end)
        row, why = await run_in_threadpool(save)
        if row:
            await websocket.send_json({"speaker": speaker, "text": row.text, "start_sec": row.start_sec,
                                       "end_sec": row.end_sec})
        elif why == "echo":
            await websocket.send_json({"speaker": speaker, "dropped": True})

    audio: asyncio.Queue = asyncio.Queue()

    # Browser messages into the queue: sound (bytes), a test sentence (fake only), or None at the end
    async def receive():
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    await audio.put(message["bytes"])
                elif message.get("text") and stt_service.config.STT_PROVIDER == "fake":
                    said = json.loads(message["text"]).get("say", "")
                    if said:
                        await audio.put(str(said))
        except Exception:                                # the line broke: treat it as the end
            pass
        await audio.put(None)

    receiver = asyncio.create_task(receive())
    try:
        await stt_service.transcribe(audio, on_sentence, speaker)
    except SttError as problem:
        await _stop(websocket, str(problem))
    except Exception:                                    # never show internal errors to the browser
        await _stop(websocket, "The transcript stopped. It reconnects by itself.")
    finally:
        receiver.cancel()
