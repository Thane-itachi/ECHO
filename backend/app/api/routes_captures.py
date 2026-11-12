"""Captures: paste a note, get proposals queued (never a memory directly)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_cipher, get_db
from app.core.crypto import AnyCipher
from app.db.models import User
from app.schemas import CaptureRequest, CaptureResponse
from app.services.captures import CaptureService

router = APIRouter(prefix="/api/captures", tags=["captures"])


@router.post("", response_model=CaptureResponse, status_code=status.HTTP_202_ACCEPTED)
def create_capture(
    payload: CaptureRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    cipher: AnyCipher = Depends(get_cipher),
) -> CaptureResponse:
    """Queue an extraction job. Duplicate text reuses the existing job."""
    job = CaptureService(db, user.id, cipher=cipher).submit(payload.text)
    return CaptureResponse(job_id=job.id, queued=job.status == "queued")
