"""The public unsubscribe link from an invitation email (no login, only the private token).

  GET  /api/unsubscribe/{token}   the person's first name and whether they already unsubscribed
  POST /api/unsubscribe/{token}   no more invitations (opening the link alone never unsubscribes)
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.features.talent_pool.schemas import UnsubscribeOut
from app.features.talent_pool.services import pool_service

router = APIRouter(prefix="/api/unsubscribe", tags=["Unsubscribe (public)"])


@router.get("/{token}", response_model=UnsubscribeOut)
def unsubscribe_page(token: str, session: Session = Depends(get_session)):
    return pool_service.unsubscribe_info(session, token)


@router.post("/{token}", response_model=UnsubscribeOut)
def unsubscribe(token: str, session: Session = Depends(get_session)):
    return pool_service.unsubscribe(session, token)
