"""Commitments: what is still owed, in either direction.

Read and write only. The intelligence that might *suggest* a commitment lives in
the proposals pipeline, which still needs an explicit approval, so nothing here
can put words in the owner's mouth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db
from app.core.crypto import ContentCipher, NullCipher
from app.db.models import User
from app.schemas import (
    CommitmentCreate,
    CommitmentList,
    CommitmentRead,
    CommitmentRemind,
    CommitmentUpdate,
    ReminderRead,
)
from app.services.commitments import CommitmentService

router = APIRouter(prefix="/api/commitments", tags=["commitments"])


def _service(db: Session, user: User, cipher: ContentCipher | NullCipher) -> CommitmentService:
    return CommitmentService(db, user.id, cipher=cipher)


@router.get("", response_model=CommitmentList)
def list_commitments(
    status_filter: str | None = Query(default="open", alias="status", pattern="^(open|done|dropped|all)$"),
    person_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> CommitmentList:
    return _service(db, user, cipher).list(
        status=None if status_filter in (None, "all") else status_filter,
        person_id=person_id,
        limit=limit,
        offset=offset,
    )


@router.get("/due", response_model=CommitmentList)
def due_commitments(
    days: int = Query(default=14, ge=1, le=365),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> CommitmentList:
    return _service(db, user, cipher).due_soon(days=days)


@router.post("", response_model=CommitmentRead, status_code=status.HTTP_201_CREATED)
def create_commitment(
    payload: CommitmentCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> CommitmentRead:
    return _service(db, user, cipher).create(payload)


@router.patch("/{commitment_id}", response_model=CommitmentRead)
def update_commitment(
    commitment_id: str,
    payload: CommitmentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> CommitmentRead:
    return _service(db, user, cipher).update(commitment_id, payload)


@router.delete("/{commitment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commitment(
    commitment_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> Response:
    _service(db, user, cipher).delete(commitment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{commitment_id}/remind", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def remind_commitment(
    commitment_id: str,
    payload: CommitmentRemind | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: ContentCipher | NullCipher = Depends(get_cipher),
) -> ReminderRead:
    """One tap: this commitment becomes a reminder, with no typing."""
    return _service(db, user, cipher).remind(commitment_id, payload or CommitmentRemind())
