"""The candidate's page (public: no login, only the private token from the invitation).

  GET /api/join/{token}    the job title, the candidate's name, the time and the status of their interview

Nothing else is shown to the candidate: no scores, notes, other candidates or the interviewer's tools.
The video call itself (F6) is added to this router later.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.interviews.schemas import JoinInfoOut
from app.features.interviews.services.invitation_service import as_utc
from app.features.jobs.models import Job

router = APIRouter(prefix="/api/join", tags=["Candidate join page"])


@router.get("/{token}", response_model=JoinInfoOut)
def join_info(token: str, session: Session = Depends(get_session)):
    interview = session.exec(select(InterviewSession).where(InterviewSession.join_token == token)).first() if len(token) >= 20 else None
    if not interview:
        raise HTTPException(404, "This interview link is not valid. Please check the link in your invitation email.")
    candidate, job = session.get(Candidate, interview.candidate_id), session.get(Job, interview.job_id)
    return JoinInfoOut(job_title=job.title if job else "", candidate_name=candidate.full_name if candidate else "",
                       scheduled_at=as_utc(interview.scheduled_at), duration_minutes=interview.duration_minutes,
                       status=interview.status)
