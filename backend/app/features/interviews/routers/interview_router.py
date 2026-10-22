"""Interviews (interviewer only).

  POST /api/sessions                      schedule an interview for a shortlisted candidate; the invitation workflow
                                          (graphs/invitation_graph.py) writes the draft and waits
  POST /api/sessions/plan                 "Suggest times": a time for each shortlisted candidate (nothing is saved)
  POST /api/sessions/template             "Write the invitation": the AI writes ONE invitation for the shortlist (to check)
  POST /api/sessions/bulk                 "Schedule and save invitations": many candidates at once, drafts only
  POST /api/sessions/send-all?job_id=3    "Send all invitations": sends every unsent draft of the job
  GET  /api/sessions?job_id=3             the interviews of a job
  GET  /api/sessions/{id}                 one interview with its invitation
  PUT  /api/sessions/{id}/time            a new time: a new draft (send it again so the candidate knows)
  POST /api/sessions/{id}/invitation      "Write again with AI": a new draft, nothing is sent
  PUT  /api/sessions/{id}/invitation      "Send email": sends the text as edited, with the calendar invite
  POST /api/sessions/{id}/start           start the video call (status live) or join it again: a LiveKit ticket
  POST /api/sessions/{id}/end             end the call for both (status ended)
  GET  /api/sessions/{id}/chat?after=12   the call chat: the messages after message 12 (0 = all)
  POST /api/sessions/{id}/chat            send a chat message as the interviewer
  GET  /api/sessions/{id}/profile         the candidate's profile and screening result (interviewer only)
  (The transcript routes are in features/transcripts.)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.interviews.models import InterviewSession
from app.features.interviews.schemas import (
    BulkOut, CallMessageOut, ChatIn, InvitationIn, PlanIn, PlanRowOut, ProfileOut, RescheduleIn, ScheduleIn,
    ScheduleManyIn, SessionOut, TemplateIn, TemplateText, TicketOut)
from app.features.interviews.services import chat_service
from app.features.interviews.services.profile_service import candidate_profile
from app.features.interviews.services.interview_service import (
    end_call, plan_times, reschedule, rewrite, schedule, schedule_many, send_all, send_invitation, session_out,
    start_call, write_template)

router = APIRouter(prefix="/api/sessions", tags=["Interviews"], dependencies=[Depends(require_interviewer)])


# Loads one interview by id or stops the request with 404; used by the routes below
def get_interview_or_404(session: Session, session_id: int) -> InterviewSession:
    interview = session.get(InterviewSession, session_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    return interview


# POST /api/sessions: schedules an interview for a shortlisted candidate and starts the invitation (schedule)
@router.post("", response_model=SessionOut, status_code=201)
def create(body: ScheduleIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return schedule(session, body.candidate_id, body.scheduled_at, body.duration_minutes, body.time_zone, email)


# POST /api/sessions/plan: suggests a time for each shortlisted candidate inside working hours (plan_times)
@router.post("/plan", response_model=list[PlanRowOut])
def plan(body: PlanIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return plan_times(session, body, email)


# POST /api/sessions/template: the AI writes ONE invitation for the shortlist, for the interviewer to check (write_template)
@router.post("/template", response_model=TemplateText)
def template(body: TemplateIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return write_template(session, body.job_id, body.duration_minutes, email)


# POST /api/sessions/bulk: schedules many candidates at once with the checked invitation; nothing is sent (schedule_many)
@router.post("/bulk", response_model=BulkOut)
def create_many(body: ScheduleManyIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return schedule_many(session, body.items, email, body.template)


# POST /api/sessions/send-all?job_id=: sends every unsent invitation of the job, after the person's Yes (send_all)
@router.post("/send-all", response_model=BulkOut)
def send_all_invitations(job_id: int, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return send_all(session, job_id, email)


# GET /api/sessions?job_id=: returns the interviews of one job, ordered by time (session_out)
@router.get("", response_model=list[SessionOut])
def list_sessions(job_id: int, session: Session = Depends(get_session)):
    rows = session.exec(select(InterviewSession).where(InterviewSession.job_id == job_id)
                        .order_by(InterviewSession.scheduled_at)).all()
    return [session_out(session, row) for row in rows]


# GET /api/sessions/{session_id}: returns one interview with its invitation draft (session_out)
@router.get("/{session_id}", response_model=SessionOut)
def get_one(session_id: int, session: Session = Depends(get_session)):
    return session_out(session, get_interview_or_404(session, session_id))


# PUT /api/sessions/{session_id}/time: saves a new time and gets a new draft (reschedule)
@router.put("/{session_id}/time", response_model=SessionOut)
def change_time(session_id: int, body: RescheduleIn, session: Session = Depends(get_session),
                email: str = Depends(current_email)):
    interview = get_interview_or_404(session, session_id)
    return reschedule(session, interview, body.scheduled_at, body.duration_minutes, body.time_zone, email)


# POST /api/sessions/{session_id}/invitation: asks the paused workflow for a new AI draft (rewrite)
@router.post("/{session_id}/invitation", response_model=SessionOut)
def write_again(session_id: int, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return rewrite(session, get_interview_or_404(session, session_id), email)


# PUT /api/sessions/{session_id}/invitation: sends the edited email and calendar invite (send_invitation)
@router.put("/{session_id}/invitation", response_model=SessionOut)
def send(session_id: int, body: InvitationIn, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return send_invitation(session, get_interview_or_404(session, session_id), body.to, body.subject, body.body, email)


# POST /api/sessions/{session_id}/start: starts or rejoins the call, returns a LiveKit ticket (start_call)
@router.post("/{session_id}/start", response_model=TicketOut)
def start(session_id: int, session: Session = Depends(get_session), email: str = Depends(current_email)):
    return start_call(session, get_interview_or_404(session, session_id), email)


# POST /api/sessions/{session_id}/end: ends the video call for both sides (end_call)
@router.post("/{session_id}/end", response_model=SessionOut)
def end(session_id: int, session: Session = Depends(get_session)):
    return end_call(session, get_interview_or_404(session, session_id))


# GET /api/sessions/{session_id}/chat: returns call chat messages after the given id (chat_service.messages)
@router.get("/{session_id}/chat", response_model=list[CallMessageOut])
def chat(session_id: int, after: int = 0, session: Session = Depends(get_session)):
    return chat_service.messages(session, get_interview_or_404(session, session_id), after)


# POST /api/sessions/{session_id}/chat: saves a chat message from the interviewer (chat_service.send)
@router.post("/{session_id}/chat", response_model=CallMessageOut)
def chat_send(session_id: int, body: ChatIn, session: Session = Depends(get_session),
              email: str = Depends(current_email)):
    return chat_service.send(session, get_interview_or_404(session, session_id), "interviewer", body.text, email)


# GET /api/sessions/{session_id}/profile: returns the candidate's profile and screening result
@router.get("/{session_id}/profile", response_model=ProfileOut)
def profile(session_id: int, session: Session = Depends(get_session)):
    return candidate_profile(session, get_interview_or_404(session, session_id))
