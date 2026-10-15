"""The live transcript: saving finished sentences, the echo guard, reading the transcript and the .txt download.

    seconds_since_start(interview)        seconds from the interview start until now (for start_sec / end_sec)
    save_turn(...)                        saves one finished sentence, or drops it (echo, empty, call not live)
    turns(session, interview, after)      the sentences after a given id, oldest first (the page asks every 2 s)
    as_text(session, interview)           the whole transcript as plain text (download); the chat is not in it

The speaker comes from the microphone the sound came from, never from the AI. The sound itself is never stored.
"""
import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession, TranscriptTurn
from app.features.interviews.schemas import TranscriptTurnOut
from app.features.jobs.models import Job

SPEAKERS = ("interviewer", "candidate")
ECHO_MIN_WORDS = 5            # shorter sentences ("Yes, I see.") are never treated as an echo
ECHO_OVERLAP = 0.8            # 80 % of the words also in the other person's sentence
ECHO_WINDOW_SEC = 6.0         # ... said within 6 seconds of it
LATE_SEC = 20                 # the last sentence may arrive a few seconds after "End interview for both"
MAX_CHARS = 2000


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)   # SQLite gives times without a zone


# Seconds from the interview start until now (0 if the call has not started)
def seconds_since_start(interview: InterviewSession) -> float:
    if not interview.started_at:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - _utc(interview.started_at)).total_seconds())


# Lower-case words without punctuation, e.g. "I used FastAPI." -> ["i", "used", "fastapi"]
def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def is_echo(session: Session, interview: InterviewSession, speaker: str, text: str, start_sec: float) -> bool:
    """True when one microphone heard the other person: 5+ words, 80 % of them in the other speaker's sentence
    from within 6 seconds. Then the sentence belongs to the other person and is not saved twice."""
    words = _words(text)
    if len(words) < ECHO_MIN_WORDS:
        return False
    nearby = session.exec(select(TranscriptTurn).where(
        TranscriptTurn.session_id == interview.id, TranscriptTurn.speaker != speaker,
        TranscriptTurn.end_sec >= start_sec - ECHO_WINDOW_SEC,
        TranscriptTurn.start_sec <= start_sec + ECHO_WINDOW_SEC)).all()
    mine = set(words)
    for other in nearby:
        shared = mine & set(_words(other.text))
        if len(shared) / len(mine) >= ECHO_OVERLAP:
            return True
    return False


def can_listen(interview: InterviewSession) -> bool:
    """While the call is live, and for a few seconds after the end (the last sentence is still on its way)."""
    if interview.status == "live":
        return True
    if interview.status == "ended" and interview.ended_at:
        return datetime.now(timezone.utc) - _utc(interview.ended_at) <= timedelta(seconds=LATE_SEC)
    return False


def save_turn(session: Session, interview_id: int, speaker: str, text: str, start_sec: float,
              end_sec: float) -> tuple[TranscriptTurn | None, str]:
    """Saves one finished sentence. Returns (the saved row, "") or (None, why it was not saved)."""
    interview = session.get(InterviewSession, interview_id)
    text = (text or "").strip()[:MAX_CHARS]
    if not interview or not can_listen(interview):
        return None, "the call is not live"
    if speaker not in SPEAKERS or not text:
        return None, "empty"
    if is_echo(session, interview, speaker, text, start_sec):
        return None, "echo"
    row = TranscriptTurn(session_id=interview.id, speaker=speaker, text=text,
                         start_sec=round(start_sec, 2), end_sec=round(max(end_sec, start_sec), 2))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, ""


def _out(row: TranscriptTurn) -> TranscriptTurnOut:
    return TranscriptTurnOut(id=row.id, speaker=row.speaker, start_sec=row.start_sec, end_sec=row.end_sec, text=row.text)


# The sentences of one interview after a sentence id, in the order they were said
def turns(session: Session, interview: InterviewSession, after: int = 0) -> list[TranscriptTurnOut]:
    rows = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == interview.id,
                                                     TranscriptTurn.id > after)
                        .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()
    return [_out(r) for r in rows]


# 65.4 -> "00:01:05"
def clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def as_text(session: Session, interview: InterviewSession) -> str:
    """Only what was said, as plain text for the download (the chat stays in its own table, call_message)."""
    candidate = session.get(Candidate, interview.candidate_id)
    job = session.get(Job, interview.job_id)
    lines = [f"Interview transcript - {job.title if job else 'job'}",
             f"Candidate: {candidate.full_name if candidate else ''}",
             f"Started: {_utc(interview.started_at).strftime('%d %b %Y, %H:%M UTC') if interview.started_at else '-'}",
             "Times are from the start of the interview. Speakers come from each person's own microphone.", ""]
    said = turns(session, interview)
    lines += [f"[{clock(t.start_sec)}] {t.speaker.capitalize()}: {t.text}" for t in said] or ["(nothing was transcribed)"]
    return "\n".join(lines) + "\n"
