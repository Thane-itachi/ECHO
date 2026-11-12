"""Owner-scoped repositories for memories, people, links and documents.

Nothing readable is written to the database any more:

* `title_enc` / `content_enc` / `notes_enc` hold ciphertext (per-user key).
* `search_index` holds keyed HMAC tokens from `BlindIndex` — the words themselves are
  never stored, so a database dump is not a readable diary. When no data key is
  configured (dev only) the index falls back to plaintext terms, which is no worse
  than the plaintext content the dev cipher is already storing.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select

from app.core.crypto import (
    AnyCipher,
    BlindIndex,
    build_blind_index,
    get_default_cipher,
)
from app.core.errors import InvalidRequest
from app.core.time import utcnow
from app.db.models import Attachment, Memory, Person, Relationship
from app.repositories.base import OwnedRepository, OwnershipViolation

_UNSET: Any = object()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _SearchableRepository(OwnedRepository):
    """Shared search plumbing: blind tokens when a key exists, plaintext in dev."""

    index_columns: tuple[str, ...] = ("search_index",)

    def __init__(
        self,
        session,
        owner_id: str,
        *,
        cipher: AnyCipher | None = None,
        blind_index: BlindIndex | None = _UNSET,  # type: ignore[assignment]
    ) -> None:
        super().__init__(session, owner_id)
        self.cipher = cipher or get_default_cipher()
        if blind_index is _UNSET:
            # Derived from the cipher, so "encrypted content" and "hashed index" can
            # never disagree: if the content is protected, the index is too.
            self.blind_index = BlindIndex.from_cipher(self.cipher) or build_blind_index()
        else:
            self.blind_index = blind_index

    # ----------------------------------------------------------------- index
    def _index(self, *texts: str) -> str:
        if self.blind_index is not None:
            return self.blind_index.index(self.owner_id, *texts)
        words = sorted({word for text in texts for word in BlindIndex.words(text or "")})
        return " " + " ".join(words) + " "

    def _search_clause(self, query: str):
        column_name = self.index_columns[0]
        column = getattr(self.model, column_name)
        if self.blind_index is not None:
            groups = self.blind_index.query_terms(self.owner_id, query)
            if not groups:
                return None
            # Every query word must appear (AND), each may match any stored token (OR).
            return and_(*[column.like(f"%{token}%") for token in groups])
        terms = [term for term in BlindIndex.words(query)][:8]
        if not terms:
            return None
        return and_(*[column.like(f"%{_escape_like(term)}%", escape="\\") for term in terms])


class MemoryRepository(_SearchableRepository):
    model = Memory
    index_columns = ("search_index",)

    # ------------------------------------------------------------- decryption
    def read_title(self, memory: Memory) -> str:
        return self.cipher.decrypt(memory.title_enc, self.owner_id)

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
            title_enc=self.cipher.encrypt(title, self.owner_id),
            content_enc=self.cipher.encrypt(content, self.owner_id),
            search_index=self._index(title, content),
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
            memory.title_enc = self.cipher.encrypt(title, self.owner_id)
        if content is not _UNSET and content is not None:
            memory.content_enc = self.cipher.encrypt(content, self.owner_id)
        if category is not _UNSET and category is not None:
            memory.category = category
        if person_id is not _UNSET:
            memory.person_id = person_id
        if confidence is not _UNSET:
            memory.confidence = confidence
        if title is not _UNSET or content is not _UNSET:
            memory.search_index = self._index(self.read_title(memory), self.read_content(memory))
        memory.updated_at = utcnow()
        return memory

    def set_archived(self, memory: Memory, *, archived: bool) -> Memory:
        if memory.user_id != self.owner_id:
            raise OwnershipViolation("refusing to archive a memory belonging to another owner")
        memory.archived_at = utcnow() if archived else None
        memory.updated_at = utcnow()
        return memory

    # ------------------------------------------------------------------ reads
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
            clause = self._search_clause(q.strip())
            if clause is not None:
                stmt = stmt.where(clause)
        stmt = stmt.order_by(Memory.created_at.desc(), Memory.id.desc())
        return self.list_page(stmt, limit=limit, offset=offset)

    def count_active(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Memory)
            .where(Memory.user_id == self.owner_id, Memory.archived_at.is_(None))
        )
        return int(self.session.scalar(stmt) or 0)


class PersonRepository(_SearchableRepository):
    model = Person

    def create(self, *, name: str, notes: str | None = None) -> Person:
        person = Person(
            user_id=self.owner_id,
            name=name,
            notes_enc=self.cipher.encrypt(notes, self.owner_id) if notes else None,
            search_index=self._index(name, notes or ""),
        )
        return self.add(person)

    def read_notes(self, person: Person) -> str | None:
        if not person.notes_enc:
            return None
        return self.cipher.decrypt(person.notes_enc, self.owner_id)

    def update(self, person: Person, *, name: Any = _UNSET, notes: Any = _UNSET) -> Person:
        if person.user_id != self.owner_id:
            raise OwnershipViolation("refusing to update a person belonging to another owner")
        if name is not _UNSET and name is not None:
            person.name = name
        if notes is not _UNSET:
            person.notes_enc = self.cipher.encrypt(notes, self.owner_id) if notes else None
        if name is not _UNSET or notes is not _UNSET:
            person.search_index = self._index(person.name, self.read_notes(person) or "")
        person.updated_at = utcnow()
        return person

    def search(self, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Person], int]:
        stmt = self.scoped_query()
        if q:
            clause = self._search_clause(q.strip())
            if clause is not None:
                stmt = stmt.where(clause)
        return self.list_page(stmt.order_by(Person.name.asc()), limit=limit, offset=offset)


class RelationshipRepository(OwnedRepository[Relationship]):
    """Memory-to-memory links. Both ends are re-checked against the owner."""

    model = Relationship

    def link(self, *, from_memory: Memory, to_memory: Memory, kind: str = "related") -> Relationship:
        for memory in (from_memory, to_memory):
            if memory.user_id != self.owner_id:
                raise OwnershipViolation("refusing to link a memory belonging to another owner")
        if from_memory.id == to_memory.id:
            raise InvalidRequest("a memory cannot be linked to itself")
        existing = self.session.scalars(
            self.scoped_query().where(
                Relationship.from_memory_id == from_memory.id,
                Relationship.to_memory_id == to_memory.id,
                Relationship.kind == kind,
            )
        ).one_or_none()
        if existing is not None:
            return existing
        relationship = Relationship(
            user_id=self.owner_id,
            from_memory_id=from_memory.id,
            to_memory_id=to_memory.id,
            kind=kind,
        )
        return self.add(relationship)

    def for_memory(self, memory_id: str) -> list[Relationship]:
        stmt = self.scoped_query().where(
            or_(Relationship.from_memory_id == memory_id, Relationship.to_memory_id == memory_id)
        )
        return list(self.session.scalars(stmt))

    def unlink(self, relationship: Relationship) -> None:
        self.delete(relationship)


class AttachmentRepository(OwnedRepository[Attachment]):
    model = Attachment

    def create(
        self,
        *,
        filename: str,
        storage_key: str,
        size_bytes: int,
        content_type: str | None,
        memory_id: str | None = None,
    ) -> Attachment:
        attachment = Attachment(
            user_id=self.owner_id,
            memory_id=memory_id,
            filename=filename,
            storage_key=storage_key,
            size_bytes=size_bytes,
            content_type=content_type,
        )
        return self.add(attachment)

    def list_for_memory(self, memory_id: str) -> list[Attachment]:
        stmt = self.scoped_query().where(Attachment.memory_id == memory_id)
        return list(self.session.scalars(stmt.order_by(Attachment.created_at.asc())))

    def search(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Attachment], int]:
        stmt = self.scoped_query().order_by(Attachment.created_at.desc())
        return self.list_page(stmt, limit=limit, offset=offset)
