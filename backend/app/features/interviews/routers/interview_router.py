"""Interviews (interviewer only).

  POST /api/sessions                      schedule an interview for a shortlisted candidate; the invitation workflow
                                          (graphs/invitation_graph.py) writes the draft and waits
  GET  /api/sessions?job_id=3             the interviews of a job
  GET  /api/sessions/{id}                 one interview with its invitation
  PUT  /api/sessions/{id}/time            a new time: a new draft (send it again so the candidate knows)
  POST /api/sessions/{id}/invitation      "Write again with AI": a new draft, nothing is sent
  PUT  /api/sessions/{id}/invitation      "Send email": sends the text as edited, with the calendar invite
  POST /api/sessions/{id}/start           start the video call (status live) or join it again: a LiveKit ticket
  POST /api/sessions/{id}/end             end the call for both (status ended)
  GET  /api/sessions/{id}/chat?after=12   the call chat: the messages after message 12 (0 = all)
  POST /api/sessions/{id}/chat            send a chat message as the interviewer
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.interviews.models import InterviewSession
from app.features.interviews.schemas import (
    CallMessageOut, ChatIn, InvitationIn, RescheduleIn, ScheduleIn, SessionOut, TicketOut)
from app.features.interviews.services import chat_service
from app.features.interviews.services.interview_service import (
    end_call, reschedule, rewrite, schedule, send_invitation, session_out, start_call)

router = APIRouter(prefix="/api/sessions", tags=["Interviews"], dependencies=[Depends(require_interviewer)])


def get_interview_or_404(session: Session, session_id: int) -> InterviewSession:
    interview = session.get(InterviewSession, session_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    return interview


@router.post("", response_model=SessionOut, status_code=201)
def create(body: ScheduleIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return schedule(session, body.candidate_id, body.scheduled_at, body.duration_minutes, body.time_zone, email)


@router.get("", response_model=list[SessionOut])
def list_sessions(job_id: int, session: Session = Depends(get_session)):
    rows = session.exec(select(InterviewSession).where(InterviewSession.job_id == job_id)
                        .order_by(InterviewSession.scheduled_at)).all()
    return [session_out(session, row) for row in rows]


@router.get("/{session_id}", response_model=SessionOut)
def get_one(session_id: int, session: Session = Depends(get_session)):
    return session_out(session, get_interview_or_404(session, session_id))


@router.put("/{session_id}/time", response_model=SessionOut)
def change_time(session_id: int, body: RescheduleIn, session: Session = Depends(get_session),
                email: str = Depends(current_email)):
    interview = get_interview_or_404(session, session_id)
    return reschedule(session, interview, body.scheduled_at, body.duration_minutes, body.time_zone, email)


@router.post("/{session_id}/invitation", response_model=SessionOut)
def write_again(session_id: int, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return rewrite(session, get_interview_or_404(session, session_id), email)


@router.put("/{session_id}/invitation", response_model=SessionOut)
def send(session_id: int, body: InvitationIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return send_invitation(session, get_interview_or_404(session, session_id), body.to, body.subject, body.body, email)


@router.post("/{session_id}/start", response_model=TicketOut)
def start(session_id: int, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return start_call(session, get_interview_or_404(session, session_id), email)


@router.post("/{session_id}/end", response_model=SessionOut)
def end(session_id: int, session: Session = Depends(get_session)):
    return end_call(session, get_interview_or_404(session, session_id))


@router.get("/{session_id}/chat", response_model=list[CallMessageOut])
def chat(session_id: int, after: int = 0, session: Session = Depends(get_session)):
    return chat_service.messages(session, get_interview_or_404(session, session_id), after)


@router.post("/{session_id}/chat", response_model=CallMessageOut)
def chat_send(session_id: int, body: ChatIn, session: Session = Depends(get_session),
              email: str = Depends(current_email)):
    return chat_service.send(session, get_interview_or_404(session, session_id), "interviewer", body.text, email)
