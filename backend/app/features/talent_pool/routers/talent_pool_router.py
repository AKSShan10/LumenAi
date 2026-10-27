"""Talent pool endpoints (interviewer only). The work is in services/pool_service.py and services/invite_service.py.

  GET    /api/candidates/{id}/talent-pool       is the candidate in the pool? (assessment report)
  PUT    /api/candidates/{id}/talent-pool       {status, note}: keep the candidate for future jobs
  DELETE /api/candidates/{id}/talent-pool       take the candidate out
  GET    /api/talent-pool                       everyone in the pool (Talent Pool page)
  GET    /api/jobs/{id}/talent-matches          past candidates who may fit this job (code, no AI), with filters:
                                                ?min_match=50&all_required=true&min_score=60&status=strong&hide_invited=true
  POST   /api/jobs/{id}/talent-invites/draft    {pool_ids, tone, instruction}: one draft per person (LangGraph)
  POST   /api/jobs/{id}/talent-invites/send     {invites}: sends the emails the interviewer checked
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core import config
from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.candidates.routers.candidate_router import get_candidate_or_404
from app.features.jobs.services.job_service import get_job_or_404
from app.features.talent_pool.schemas import (DraftIn, InviteDraft, InviteResult, MatchesOut, PoolEntryIn, PoolEntryOut,
                                              PoolRow, SendIn)
from app.features.talent_pool.services import invite_service, pool_service

router = APIRouter(prefix="/api", tags=["Talent pool"], dependencies=[Depends(require_interviewer)])


@router.get("/candidates/{candidate_id}/talent-pool", response_model=PoolEntryOut)
def pool_entry(candidate_id: int, session: Session = Depends(get_session)):
    return pool_service.entry(session, get_candidate_or_404(session, candidate_id))


@router.put("/candidates/{candidate_id}/talent-pool", response_model=PoolEntryOut)
def add_to_pool(candidate_id: int, body: PoolEntryIn, session: Session = Depends(get_session),
                email: str = Depends(current_email)):
    return pool_service.add(session, get_candidate_or_404(session, candidate_id), body, email)


@router.delete("/candidates/{candidate_id}/talent-pool", response_model=PoolEntryOut)
def remove_from_pool(candidate_id: int, session: Session = Depends(get_session)):
    return pool_service.remove(session, get_candidate_or_404(session, candidate_id))


@router.get("/talent-pool", response_model=list[PoolRow])
def talent_pool(session: Session = Depends(get_session)):
    return pool_service.pool(session)


@router.get("/jobs/{job_id}/talent-matches", response_model=MatchesOut)
def talent_matches(job_id: int, min_match: Optional[int] = Query(None, ge=0, le=100), all_required: bool = False,
                   min_score: Optional[float] = Query(None, ge=0, le=100),
                   status: Optional[Literal["strong", "other_role"]] = None, hide_invited: bool = False,
                   session: Session = Depends(get_session)):
    limit = config.POOL_MIN_MATCH if min_match is None else min_match
    rows = pool_service.matches(session, get_job_or_404(session, job_id), limit, all_required, min_score, status,
                                hide_invited)
    return MatchesOut(min_match=limit, rows=rows)


@router.post("/jobs/{job_id}/talent-invites/draft", response_model=list[InviteDraft])
def draft_invites(job_id: int, body: DraftIn, session: Session = Depends(get_session),
                  email: str = Depends(current_email)):
    return invite_service.drafts(session, get_job_or_404(session, job_id), body, email)


@router.post("/jobs/{job_id}/talent-invites/send", response_model=list[InviteResult])
def send_invites(job_id: int, body: SendIn, session: Session = Depends(get_session),
                 email: str = Depends(current_email)):
    return invite_service.send(session, get_job_or_404(session, job_id), body.invites, email)
