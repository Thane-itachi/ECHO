from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.db.models import User
from app.schemas import ReminderCreate, ReminderList, ReminderRead
from app.services.reminders import ReminderService

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=ReminderList)
def list_reminders(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReminderList:
    return ReminderService(db, user.id).list(limit=limit, offset=offset)


@router.post("", response_model=ReminderRead, status_code=201)
def create_reminder(
    payload: ReminderCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReminderRead:
    return ReminderService(db, user.id).create(payload)


@router.post("/{reminder_id}/cancel", response_model=ReminderRead)
def cancel_reminder(
    reminder_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReminderRead:
    return ReminderService(db, user.id).cancel(reminder_id)
