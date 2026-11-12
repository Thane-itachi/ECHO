from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.db.models import User
from app.repositories.system import AuditRepository
from app.schemas import ReminderCreate, ReminderList, ReminderRead
from app.services import reminder_email
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


# --- reminder email opt-out ---------------------------------------------------------
# These two routes are deliberately public: the link arrives in a mail client, where
# there is no session. The signed token in the URL is the whole credential, and it can
# only do one thing: change the reminder-email flag for the account it names.

NOT_VALID = (
    "This link does not belong to any ECHO account. If you want to stop reminder "
    "emails, open ECHO and use the switch in the sidebar."
)


def _account(db: Session, token: str) -> User | None:
    try:
        user_id = reminder_email.user_id_from_token(token)
    except reminder_email.BadToken:
        return None
    return db.get(User, user_id)


@router.get("/email/opt-out", response_class=HTMLResponse)
def opt_out_page(token: str = Query(default=""), db: Session = Depends(get_db)) -> HTMLResponse:
    """Ask before acting: mail scanners fetch every link in a message."""
    user = _account(db, token)
    if user is None:
        return HTMLResponse(
            reminder_email.page(heading="That link is not valid", text=NOT_VALID), status_code=404
        )
    if user.reminder_email_enabled:
        return HTMLResponse(
            reminder_email.page(
                heading="Turn off reminder emails?",
                text="Your reminders will still be scheduled and still appear in ECHO. "
                "You just will not be emailed about them.",
                button="Turn them off",
                action="off",
                token=token,
            )
        )
    return HTMLResponse(
        reminder_email.page(
            heading="Reminder emails are already off",
            text="Nothing more to do. If you change your mind, you can turn them back on here.",
            button="Turn them back on",
            action="on",
            token=token,
        )
    )


@router.post("/email/opt-out", response_class=HTMLResponse)
def opt_out_apply(
    token: str = Form(default=""),
    action: str = Form(default="off"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    user = _account(db, token)
    if user is None:
        return HTMLResponse(
            reminder_email.page(heading="That link is not valid", text=NOT_VALID), status_code=404
        )
    enable = action == "on"
    if user.reminder_email_enabled != enable:
        user.reminder_email_enabled = enable
        AuditRepository(db).record(
            action="reminder_email.enabled" if enable else "reminder_email.disabled",
            actor_id=user.id,
            actor_type="system",
            target_type="user",
            target_id=user.id,
            detail={"via": "email link"},
        )
        db.commit()
    if enable:
        return HTMLResponse(
            reminder_email.page(
                heading="Reminder emails are back on",
                text="ECHO will email you when a reminder comes due. You can turn them off "
                "again from any of those messages, or in the sidebar.",
            )
        )
    return HTMLResponse(
        reminder_email.page(
            heading="Reminder emails are off",
            text="You will not be emailed about reminders any more. Your reminders are "
            "still scheduled and still in ECHO. To turn emails back on, use the switch "
            "in the sidebar, or the button below.",
            button="Turn them back on",
            action="on",
            token=token,
        )
    )
