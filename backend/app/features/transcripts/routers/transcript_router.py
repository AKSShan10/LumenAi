"""Reading the transcript (interviewer only, login needed).

  GET /api/sessions/{id}/transcript?after=12   the sentences after sentence 12 (0 = all); the page asks every 2 s
  GET /api/sessions/{id}/transcript.txt        the whole transcript as a text file (download)

The microphones themselves use the WebSockets in stt_router.py.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.interviews.routers.interview_router import get_interview_or_404
from app.features.transcripts.schemas import TranscriptTurnOut
from app.features.transcripts.services import transcript_service

router = APIRouter(prefix="/api/sessions", tags=["Transcripts"], dependencies=[Depends(require_interviewer)])


@router.get("/{session_id}/transcript", response_model=list[TranscriptTurnOut])
def transcript(session_id: int, after: int = 0, session: Session = Depends(get_session)):
    """The transcript sentences after the given id, in the order they were said (transcript_service.turns)."""
    return transcript_service.turns(session, get_interview_or_404(session, session_id), after)


@router.get("/{session_id}/transcript.txt", response_class=PlainTextResponse)
def transcript_file(session_id: int, session: Session = Depends(get_session)):
    """The transcript as a downloadable text file (transcript_service.as_text)."""
    interview = get_interview_or_404(session, session_id)
    return PlainTextResponse(transcript_service.as_text(session, interview),
                             headers={"Content-Disposition": f'attachment; filename="interview-{interview.id}-transcript.txt"'})
