from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.crypto import CipherError, ContentCipher, NullCipher, get_default_cipher
from app.core.time import utcnow
from app.db.models import Memory, Person
from app.repositories.base import OwnedRepository, OwnershipViolation

_UNSET: Any = object()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MemoryRepository(OwnedRepository[Memory]):
    model = Memory

    def __init__(self, session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        super().__init__(session, owner_id)
        self.cipher = cipher or get_default_cipher()

    # ------------------------------------------------------------- encryption
    @staticmethod
    def _index_text(title: str, content: str) -> str:
        """The single place searchable text is derived. Swap here for E2EE search."""
        return f"{title}\n{content}".lower()

    def read_content(self, memory: Memory) -> str:
        return self.cipher.decrypt(memory.content_enc, self.owner_id)

    # ----------------------------------------------------------------- writes
    def create(
        self,
        *,
        title: str,
        content: str,
        category: str = "general",
        person_id: str | None = None,
        source: str = "user",
        confidence: float | None = None,
    ) -> Memory:
        memory = Memory(
            user_id=self.owner_id,
            title=title,
            content_enc=self.cipher.encrypt(content, self.owner_id),
            search_text=self._index_text(title, content),
            category=category,
            person_id=person_id,
            source=source,
            confidence=confidence,
        )
        return self.add(memory)

    def update(
        self,
        memory: Memory,
        *,
        title: Any = _UNSET,
        content: Any = _UNSET,
        category: Any = _UNSET,
        person_id: Any = _UNSET,
        confidence: Any = _UNSET,
    ) -> Memory:
        if memory.user_id != self.owner_id:
            raise OwnershipViolation("refusing to update a memory belonging to another owner")
        if title is not _UNSET and title is not None:
            memory.title = title
        if content is not _UNSET and content is not None:
            memory.content_enc = self.cipher.encrypt(content, self.owner_id)
        if category is not _UNSET and category is not None:
            memory.category = category
        if person_id is not _UNSET:
            memory.person_id = person_id
        if confidence is not _UNSET:
            memory.confidence = confidence
        if title is not _UNSET or content is not _UNSET:
            memory.search_text = self._index_text(memory.title, self.read_content(memory))
        memory.updated_at = utcnow()
        return memory

    def set_archived(self, memory: Memory, *, archived: bool) -> Memory:
        if memory.user_id != self.owner_id:
            raise OwnershipViolation("refusing to archive a memory belonging to another owner")
        memory.archived_at = utcnow() if archived else None
        memory.updated_at = utcnow()
        return memory

    # ----------------------------------------------------------------- reads
    def search(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Memory], int]:
        stmt = self.scoped_query()
        if not include_archived:
            stmt = stmt.where(Memory.archived_at.is_(None))
        if category:
            stmt = stmt.where(Memory.category == category)
        if q:
            needle = _escape_like(q.strip().lower())
            stmt = stmt.where(Memory.search_text.like(f"%{needle}%", escape="\\"))
        stmt = stmt.order_by(Memory.created_at.desc(), Memory.id.desc())
        return self.list_page(stmt, limit=limit, offset=offset)

    def count_active(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Memory)
            .where(Memory.user_id == self.owner_id, Memory.archived_at.is_(None))
        )
        return int(self.session.scalar(stmt) or 0)


class PersonRepository(OwnedRepository[Person]):
    model = Person

    def create(self, *, name: str, notes: str | None = None) -> Person:
        person = Person(
            user_id=self.owner_id,
            name=name,
            notes_enc=None,
            search_text=name.lower(),
        )
        if notes:
            person.notes_enc = notes  # people notes are short free text; see README tradeoff
            person.search_text = f"{name}\n{notes}".lower()
        return self.add(person)

    def search(self, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Person], int]:
        stmt = self.scoped_query()
        if q:
            needle = _escape_like(q.strip().lower())
            stmt = stmt.where(Person.search_text.like(f"%{needle}%", escape="\\"))
        return self.list_page(stmt.order_by(Person.name.asc()), limit=limit, offset=offset)
