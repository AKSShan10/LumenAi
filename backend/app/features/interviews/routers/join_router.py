"""The candidate's page (public: no login, only the private token from the invitation).

  GET  /api/join/{token}          the job title, the candidate's name, the time and the status of their interview
  POST /api/join/{token}/ticket   {name}: a ticket to join the video call, only while the interviewer has it open
  GET  /api/join/{token}/chat?after=12   the call chat of this interview only
  POST /api/join/{token}/chat     send a chat message as the candidate (only while the call is live)

Nothing else is shown to the candidate: no scores, notes, other candidates or the interviewer's tools.
The candidate's ticket allows only their own room (signed by the backend, see video_service.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.interviews.schemas import CallMessageOut, ChatIn, JoinInfoOut, JoinTicketIn, TicketOut
from app.features.interviews.services import chat_service
from app.features.interviews.services.interview_service import candidate_ticket
from app.features.interviews.services.invitation_service import as_utc
from app.features.jobs.models import Job

router = APIRouter(prefix="/api/join", tags=["Candidate join page"])


# Finds the interview by the private join token from the email link, or stops with 404
def interview_of(session: Session, token: str) -> InterviewSession:
    interview = session.exec(select(InterviewSession).where(InterviewSession.join_token == token)).first() if len(token) >= 20 else None
    if not interview:
        raise HTTPException(404, "This interview link is not valid. Please check the link in your invitation email.")
    return interview


# GET /api/join/{token}: returns only job title, candidate name, time and status for the candidate page
@router.get("/{token}", response_model=JoinInfoOut)
def join_info(token: str, session: Session = Depends(get_session)):
    interview = interview_of(session, token)
    candidate, job = session.get(Candidate, interview.candidate_id), session.get(Job, interview.job_id)
    return JoinInfoOut(job_title=job.title if job else "", candidate_name=candidate.full_name if candidate else "",
                       scheduled_at=as_utc(interview.scheduled_at), duration_minutes=interview.duration_minutes,
                       status=interview.status)


# POST /api/join/{token}/ticket: gives the candidate a LiveKit ticket while the call is live
@router.post("/{token}/ticket", response_model=TicketOut)
def join_ticket(token: str, body: JoinTicketIn, session: Session = Depends(get_session)):
    return candidate_ticket(session, interview_of(session, token), body.name)


# GET /api/join/{token}/chat: returns the call chat of this interview for the candidate
@router.get("/{token}/chat", response_model=list[CallMessageOut])
def join_chat(token: str, after: int = 0, session: Session = Depends(get_session)):
    return chat_service.messages(session, interview_of(session, token), after)


# POST /api/join/{token}/chat: saves a chat message from the candidate (only while live)
@router.post("/{token}/chat", response_model=CallMessageOut)
def join_chat_send(token: str, body: ChatIn, session: Session = Depends(get_session)):
    return chat_service.send(session, interview_of(session, token), "candidate", body.text)
