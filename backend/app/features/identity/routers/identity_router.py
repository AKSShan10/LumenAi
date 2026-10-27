"""Candidate identification (F7), interviewer only. The work is in services/identity_service.py.

  GET  /api/sessions/{id}/identity           the identity status shown in the interviewer's room
  POST /api/sessions/{id}/identity/check     one camera picture (form field "frame") is compared with the photos
  PUT  /api/sessions/{id}/identity/decision  the interviewer confirms or rejects ({"decision": "confirmed"})
  GET  /api/candidates/{id}/photo            the photo from the application
The candidate's page never calls these.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.candidates.routers.candidate_router import get_candidate_or_404
from app.features.candidates.services.cv_storage_service import photo_file
from app.features.identity.schemas import DecisionIn, IdentityOut
from app.features.identity.services import identity_service
from app.features.interviews.routers.interview_router import get_interview_or_404

router = APIRouter(prefix="/api", tags=["Candidate identification"], dependencies=[Depends(require_interviewer)])
MAX_FRAME_BYTES = 3 * 1024 * 1024


@router.get("/sessions/{session_id}/identity", response_model=IdentityOut)
def get_identity(session_id: int, session: Session = Depends(get_session)):
    """GET /api/sessions/{id}/identity: the identity status of this interview."""
    return identity_service.result(session, get_interview_or_404(session, session_id))


@router.post("/sessions/{session_id}/identity/check", response_model=IdentityOut)
async def check_identity(session_id: int, frame: UploadFile = File(...), session: Session = Depends(get_session)):
    """POST /api/sessions/{id}/identity/check: compares one camera picture (form field "frame")."""
    data = await frame.read(MAX_FRAME_BYTES + 1)
    if not data or len(data) > MAX_FRAME_BYTES:
        raise HTTPException(422, "Send one camera picture (JPG or PNG, at most 3 MB).")
    return identity_service.check(session, get_interview_or_404(session, session_id), data)


@router.put("/sessions/{session_id}/identity/decision", response_model=IdentityOut)
def decide_identity(session_id: int, body: DecisionIn, session: Session = Depends(get_session),
                    email: str = Depends(current_email)):
    """PUT /api/sessions/{id}/identity/decision: the interviewer confirms, rejects or takes back."""
    return identity_service.decide(session, get_interview_or_404(session, session_id), body.decision, email)


@router.get("/candidates/{candidate_id}/photo")
def get_photo(candidate_id: int, session: Session = Depends(get_session)):
    """GET /api/candidates/{id}/photo: the photo from the application (404 when there is none)."""
    candidate = get_candidate_or_404(session, candidate_id)
    path = photo_file(candidate)
    if not path:
        raise HTTPException(404, "No photo for this candidate.")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
