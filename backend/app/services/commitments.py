"""Commitments: promises, things lent, things borrowed.

The rule the rest of ECHO lives by applies here too: a commitment is a row the
owner wrote or approved, never something the software decided they owed. The
service only reads what is stored, keeps it owner-scoped, and turns one into a
reminder when asked - it never invents a due date.

A commitment is not a calendar entry. It can carry a day so it can become a
reminder in one tap, but "Daniel has my drill" with no date is a perfectly good
commitment, and it is the one people forget.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.crypto import ContentCipher, NullCipher, get_default_cipher
from app.core.errors import InvalidRequest
from app.core.time import as_utc, utcnow
from app.repositories.memories import (
    CommitmentRepository,
    MemoryRepository,
    PersonRepository,
)
from app.schemas import (
    CommitmentCreate,
    CommitmentList,
    CommitmentRead,
    CommitmentRemind,
    CommitmentUpdate,
    ReminderCreate,
    ReminderRead,
)
from app.services.reminders import ReminderService
from app.services.serializers import to_commitment_read

#: A dated commitment becomes a reminder at nine in the morning, UTC, unless the
#: caller says otherwise. Early enough to act on, late enough not to wake anyone.
DEFAULT_REMINDER_HOUR = 9


class CommitmentService:
    def __init__(self, session: Session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.commitments = CommitmentRepository(session, owner_id, cipher=self.cipher)
        self.people = PersonRepository(session, owner_id, cipher=self.cipher)
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)

    # ------------------------------------------------------------------ read
    def list(
        self,
        *,
        status: str | None = "open",
        person_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CommitmentList:
        if person_id:
            self.people.require(person_id)
        rows, total = self.commitments.page(status=status, person_id=person_id, limit=limit, offset=offset)
        names = self._names()
        return CommitmentList(
            items=[to_commitment_read(row, self.commitments, person_name=names.get(row.person_id or "")) for row in rows],
            total=total,
        )

    def due_soon(self, *, days: int = 14, limit: int = 20) -> CommitmentList:
        """What falls due next: the dashboard's "people" block reads this."""
        today = utcnow().date()
        rows = self.commitments.due_between(start=today, end=today + timedelta(days=days), limit=limit)
        names = self._names()
        return CommitmentList(
            items=[to_commitment_read(row, self.commitments, person_name=names.get(row.person_id or "")) for row in rows],
            total=len(rows),
        )

    # ----------------------------------------------------------------- write
    def create(self, payload: CommitmentCreate) -> CommitmentRead:
        if payload.person_id:
            self.people.require(payload.person_id)
        if payload.memory_id:
            self.memories.require(payload.memory_id)
        row = self.commitments.create(
            text=payload.text.strip(),
            kind=payload.kind,
            person_id=payload.person_id,
            memory_id=payload.memory_id,
            due_on=payload.due_on,
        )
        self.session.commit()
        return to_commitment_read(row, self.commitments, person_name=self._name_for(row.person_id))

    def update(self, commitment_id: str, payload: CommitmentUpdate) -> CommitmentRead:
        row = self.commitments.require(commitment_id)
        if payload.text is not None:
            row.text_enc = self.commitments.cipher.encrypt(payload.text.strip(), self.owner_id)
        if "due_on" in payload.model_fields_set:
            row.due_on = payload.due_on
        if payload.status is not None:
            row.status = payload.status
        row.updated_at = utcnow()
        self.session.commit()
        return to_commitment_read(row, self.commitments, person_name=self._name_for(row.person_id))

    def delete(self, commitment_id: str) -> None:
        row = self.commitments.require(commitment_id)
        self.commitments.delete(row)
        self.session.commit()

    def remind(self, commitment_id: str, payload: CommitmentRemind) -> ReminderRead:
        row = self.commitments.require(commitment_id)
        due_at = self._reminder_time(row.due_on, payload.due_at)
        if due_at <= utcnow():
            raise InvalidRequest("that commitment is already due; pick a time in the future")

        person_name = self._name_for(row.person_id)
        text = self.commitments.read_text(row)
        title = f"{person_name}: {text}" if person_name else text
        reminder = ReminderService(self.session, self.owner_id).create(
            ReminderCreate(
                title=title[:200],
                due_at=due_at,
                memory_id=row.memory_id,
                # one reminder per commitment per day: a second press does not
                # send a second notification
                client_request_id=f"commitment-{row.id}-{due_at.date().isoformat()}",
            )
        )
        return reminder

    # --------------------------------------------------------------- helpers
    def _reminder_time(self, due_on: date | None, asked: datetime | None) -> datetime:
        if asked is not None:
            return as_utc(asked)
        day = due_on or (utcnow().date() + timedelta(days=1))
        return datetime.combine(day, time(hour=DEFAULT_REMINDER_HOUR))

    def _names(self) -> dict[str, str]:
        rows, _ = self.people.search(limit=200, offset=0)
        return {person.id: person.name for person in rows}

    def _name_for(self, person_id: str | None) -> str | None:
        if not person_id:
            return None
        try:
            return self.people.require(person_id).name
        except Exception:  # a person deleted between write and read is not an error
            return None
