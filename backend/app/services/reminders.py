"""Reminders: create row + one job at the due instant, nothing scheduled in-process."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidRequest
from app.core.time import as_utc, utcnow
from app.db.models import Reminder
from app.repositories.base import OwnedRepository
from app.repositories.memories import MemoryRepository
from app.repositories.system import AuditRepository
from app.schemas import ReminderCreate, ReminderList, ReminderRead
from app.services.jobs import enqueue_job
from app.services.serializers import to_reminder_read


class ReminderRepository(OwnedRepository[Reminder]):
    model = Reminder

    def create(self, *, title: str, due_at, memory_id: str | None, client_request_id: str | None) -> Reminder:
        reminder = Reminder(
            user_id=self.owner_id,
            title=title,
            due_at=due_at,
            memory_id=memory_id,
            client_request_id=client_request_id,
            status="scheduled",
        )
        return self.add(reminder)

    def by_client_request_id(self, client_request_id: str) -> Reminder | None:
        return self.session.scalars(
            self.scoped_query().where(Reminder.client_request_id == client_request_id)
        ).one_or_none()

    def due(self, *, limit: int = 50) -> list[Reminder]:
        from sqlalchemy import select

        return list(
            self.session.scalars(
                select(Reminder)
                .where(Reminder.user_id == self.owner_id, Reminder.status == "scheduled", Reminder.due_at <= utcnow())
                .order_by(Reminder.due_at.asc())
                .limit(limit)
            )
        )

    def list_page_default(self, *, limit: int, offset: int):
        return self.list_page(self.scoped_query().order_by(Reminder.due_at.asc()), limit=limit, offset=offset)


class ReminderService:
    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.reminders = ReminderRepository(session, owner_id)
        self.memories = MemoryRepository(session, owner_id)
        self.audit = AuditRepository(session)

    def create(self, payload: ReminderCreate) -> ReminderRead:
        due_at = as_utc(payload.due_at)
        if due_at <= utcnow():
            raise InvalidRequest("due_at must be in the future")
        if payload.memory_id:
            self.memories.require(payload.memory_id)
        if payload.client_request_id:
            existing = self.reminders.by_client_request_id(payload.client_request_id)
            if existing is not None:
                return to_reminder_read(existing)

        reminder = self.reminders.create(
            title=payload.title.strip(),
            due_at=due_at,
            memory_id=payload.memory_id,
            client_request_id=payload.client_request_id,
        )
        try:
            self.session.flush()
        except IntegrityError as exc:  # concurrent retry with the same client_request_id
            self.session.rollback()
            existing = self.reminders.by_client_request_id(payload.client_request_id or "")
            if existing is None:
                raise Conflict("reminder could not be created") from exc
            return to_reminder_read(existing)

        # Exactly-once basis for the notification itself.
        reminder.notification_key = f"reminder:{reminder.id}:{due_at.isoformat()}"
        enqueue_job(
            self.session,
            kind="reminder.notify",
            run_at=due_at,
            payload={"reminder_id": reminder.id, "user_id": self.owner_id},
            idempotency_key=f"job:{reminder.notification_key}",
        )
        self.audit.record(
            action="reminder.created",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="reminder",
            target_id=reminder.id,
            detail={"due_at": due_at.isoformat()},
        )
        self.session.commit()
        return to_reminder_read(reminder)

    def list(self, *, limit: int = 50, offset: int = 0) -> ReminderList:
        rows, total = self.reminders.list_page_default(limit=limit, offset=offset)
        return ReminderList(items=[to_reminder_read(r) for r in rows], total=total, limit=limit, offset=offset)

    def cancel(self, reminder_id: str) -> ReminderRead:
        reminder = self.reminders.require(reminder_id)
        reminder.status = "cancelled"
        self.audit.record(
            action="reminder.cancelled",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="reminder",
            target_id=reminder.id,
        )
        self.session.commit()
        return to_reminder_read(reminder)
