from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db
from app.core.crypto import ContentCipher, NullCipher
from app.db.models import User
from app.schemas import ProposalCreate, ProposalDecision, ProposalList, ProposalRead
from app.services.proposals import ProposalService

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("", response_model=ProposalList)
def list_proposals(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ProposalList:
    return ProposalService(db, user.id, cipher=cipher).list(status=status, limit=limit, offset=offset)


@router.post("", response_model=ProposalRead, status_code=201)
def create_proposal(
    payload: ProposalCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ProposalRead:
    """Target of the extraction worker. Writes a pending proposal, never a memory."""
    return ProposalService(db, user.id, cipher=cipher).create(payload)


@router.get("/{proposal_id}", response_model=ProposalRead)
def get_proposal(
    proposal_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ProposalRead:
    return ProposalService(db, user.id, cipher=cipher).get(proposal_id)


@router.post("/{proposal_id}/approve", response_model=ProposalDecision)
def approve_proposal(
    proposal_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ProposalDecision:
    return ProposalService(db, user.id, cipher=cipher).approve(proposal_id)


@router.post("/{proposal_id}/reject", response_model=ProposalDecision)
def reject_proposal(
    proposal_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ProposalDecision:
    return ProposalService(db, user.id, cipher=cipher).reject(proposal_id)
