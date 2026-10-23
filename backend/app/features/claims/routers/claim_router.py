"""CV claim verification (F8), interviewer only. The work is in services/claim_service.py and graphs/claim_check_graph.py.

  POST /api/candidates/{id}/claims   "Check CV claims": answers 202 at once, the work runs in the background
  GET  /api/candidates/{id}/claims   the claims and their status; the page asks every 3 seconds while "running"
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import require_interviewer
from app.features.candidates.routers.candidate_router import get_candidate_or_404
from app.features.claims.schemas import ClaimCheckOut
from app.features.claims.services import claim_service

router = APIRouter(prefix="/api", tags=["CV claim verification"], dependencies=[Depends(require_interviewer)])


@router.post("/candidates/{candidate_id}/claims", response_model=ClaimCheckOut, status_code=202)
def start_claim_check(candidate_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    started = claim_service.start(session, get_candidate_or_404(session, candidate_id))
    background.add_task(claim_service.run, candidate_id)        # → runs after the answer is sent
    return started


@router.get("/candidates/{candidate_id}/claims", response_model=ClaimCheckOut)
def get_claim_check(candidate_id: int, session: Session = Depends(get_session)):
    return claim_service.result(session, get_candidate_or_404(session, candidate_id))
