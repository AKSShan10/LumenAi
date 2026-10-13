"""The chat inside the video call: the interviewer and the candidate send text and links to each other.

    messages(session, interview, after)        the messages after a message id (0 = all), oldest first
    send(session, interview, sender, text, by) saves one message from "interviewer" or "candidate"

Each message keeps both the role (interviewer | candidate) and the sender's name. The chat shows the name;
the role tells the two sides apart (for example in a transcript later). The name is saved when the message is sent:
the interviewer's full name from their account (`by` = their login email), the candidate's name from their
application. Without a name the chat shows "Interviewer" or "Candidate".

Both sides ask for new messages every few seconds (no WebSocket needed). The text is saved and shown as plain text;
the page turns web addresses into links. The AI does not read or write here.
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.auth.models import User
from app.features.candidates.models import Candidate
from app.features.interviews.models import CallMessage, InterviewSession
from app.features.interviews.schemas import CallMessageOut
from app.features.interviews.services.invitation_service import as_utc

MAX_CHARS = 1000


# Finds the sender's name: the interviewer's account name or the candidate's name
def _name_of(session: Session, interview: InterviewSession, sender: str, by: str) -> str:
    if sender == "interviewer":
        user = session.exec(select(User).where(User.email == by)).first()
        return (user.full_name or "") if user else ""
    candidate = session.get(Candidate, interview.candidate_id)
    return (candidate.full_name or "") if candidate else ""


# Turns a saved chat row into CallMessageOut; shows 'Interviewer'/'Candidate' when no name
def _out(row: CallMessage) -> CallMessageOut:
    shown = row.sender_name or row.sender.capitalize()          # "Interviewer" / "Candidate" when no name was saved
    return CallMessageOut(id=row.id, sender=row.sender, sender_name=shown, text=row.text, sent_at=as_utc(row.sent_at))


# Returns the call chat messages of one interview after a message id, oldest first
def messages(session: Session, interview: InterviewSession, after: int = 0) -> list[CallMessageOut]:
    rows = session.exec(select(CallMessage).where(CallMessage.session_id == interview.id, CallMessage.id > after)
                        .order_by(CallMessage.id)).all()
    return [_out(r) for r in rows]


def send(session: Session, interview: InterviewSession, sender: str, text: str, by: str = "") -> CallMessageOut:
    """The interviewer can write before and during the call; the candidate only while it is live. Nobody after the end."""
    if interview.status == "ended":
        raise HTTPException(400, "This interview has ended; the chat is closed.")
    if sender == "candidate" and interview.status != "live":
        raise HTTPException(409, "The chat opens when the interviewer starts the interview.")
    text = text.strip()
    if not text:
        raise HTTPException(422, "The message is empty.")
    row = CallMessage(session_id=interview.id, sender=sender, sender_name=_name_of(session, interview, sender, by),
                      text=text[:MAX_CHARS])
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)
