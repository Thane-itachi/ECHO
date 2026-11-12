"""Memory service: every method starts from an owner-scoped repository."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import ContentCipher, NullCipher, get_default_cipher
from app.repositories.memories import (
    MemoryRepository,
    PersonRepository,
    RelationshipRepository,
)
from app.repositories.system import AuditRepository
from app.schemas import (
    LinkCreate,
    LinkedMemory,
    LinkList,
    MemoryCreate,
    MemoryList,
    MemoryRead,
    MemoryUpdate,
    PersonCreate,
    PersonList,
    PersonRead,
)
from app.services.serializers import to_memory_read, to_person_read


class MemoryService:
    def __init__(self, session: Session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.memories = MemoryRepository(session, owner_id, cipher=self.cipher)
        self.people = PersonRepository(session, owner_id, cipher=self.cipher)
        self.links = RelationshipRepository(session, owner_id)
        self.audit = AuditRepository(session)

    def create(self, payload: MemoryCreate) -> MemoryRead:
        if payload.person_id:
            # Cross-tenant guard: a person id belonging to someone else is simply not found.
            self.people.require(payload.person_id)
        memory = self.memories.create(
            title=payload.title,
            content=payload.content,
            category=payload.category.value,
            person_id=payload.person_id,
        )
        self.session.flush()
        self.audit.record(
            action="memory.created",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="memory",
            target_id=memory.id,
            detail={"category": memory.category},
        )
        self.session.commit()
        return to_memory_read(memory, self.memories)

    def get(self, memory_id: str) -> MemoryRead:
        return to_memory_read(self.memories.require(memory_id), self.memories)

    def list(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryList:
        rows, total = self.memories.search(
            q=q, category=category, include_archived=include_archived, limit=limit, offset=offset
        )
        return MemoryList(
            items=[to_memory_read(row, self.memories) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def update(self, memory_id: str, payload: MemoryUpdate) -> MemoryRead:
        memory = self.memories.require(memory_id)
        patch: dict[str, Any] = payload.model_dump(exclude_unset=True)
        if "category" in patch and patch["category"] is not None:
            patch["category"] = patch["category"].value
        if "person_id" in patch and patch["person_id"]:
            self.people.require(patch["person_id"])
        self.memories.update(memory, **patch)
        self.session.flush()
        self.audit.record(
            action="memory.updated",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="memory",
            target_id=memory.id,
            detail={"fields": sorted(patch.keys())},
        )
        self.session.commit()
        return to_memory_read(memory, self.memories)

    def set_archived(self, memory_id: str, *, archived: bool) -> MemoryRead:
        memory = self.memories.require(memory_id)
        self.memories.set_archived(memory, archived=archived)
        self.audit.record(
            action="memory.archived" if archived else "memory.restored",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="memory",
            target_id=memory.id,
        )
        self.session.commit()
        return to_memory_read(memory, self.memories)

    def delete(self, memory_id: str) -> None:
        memory = self.memories.require(memory_id)
        self.memories.delete(memory)
        self.audit.record(
            action="memory.deleted",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="memory",
            target_id=memory_id,
        )
        self.session.commit()


    # ------------------------------------------------------------------- links
    def _link_list(self, memory_id: str) -> LinkList:
        items: list[LinkedMemory] = []
        for relationship in self.links.for_memory(memory_id):
            other_id = (
                relationship.to_memory_id
                if relationship.from_memory_id == memory_id
                else relationship.from_memory_id
            )
            other = self.memories.require(other_id)
            items.append(
                LinkedMemory(id=other.id, title=self.memories.read_title(other), kind=relationship.kind)
            )
        return LinkList(items=items)

    def link(self, memory_id: str, payload: LinkCreate) -> LinkList:
        memory = self.memories.require(memory_id)
        target = self.memories.require(payload.to_memory_id)  # cross-tenant ids are 404
        self.links.link(from_memory=memory, to_memory=target, kind=payload.kind)
        self.session.flush()
        self.audit.record(
            action="memory.linked",
            actor_id=self.owner_id,
            actor_type="user",
            target_type="memory",
            target_id=memory.id,
            detail={"to": target.id, "kind": payload.kind},
        )
        self.session.commit()
        return self._link_list(memory_id)

    def list_links(self, memory_id: str) -> LinkList:
        self.memories.require(memory_id)
        return self._link_list(memory_id)

    def unlink(self, memory_id: str, other_id: str) -> LinkList:
        memory = self.memories.require(memory_id)
        for relationship in self.links.for_memory(memory_id):
            if other_id in (relationship.from_memory_id, relationship.to_memory_id):
                self.links.unlink(relationship)
        self.session.commit()
        return self._link_list(memory.id)


class PersonService:
    def __init__(self, session: Session, owner_id: str, *, cipher: ContentCipher | NullCipher | None = None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.cipher = cipher or get_default_cipher()
        self.people = PersonRepository(session, owner_id, cipher=self.cipher)

    def create(self, payload: PersonCreate) -> PersonRead:
        person = self.people.create(name=payload.name.strip(), notes=payload.notes)
        self.session.commit()
        return to_person_read(person, self.people)

    def list(self, *, limit: int = 50, offset: int = 0) -> PersonList:
        rows, total = self.people.search(limit=limit, offset=offset)
        return PersonList(
            items=[to_person_read(row, self.people) for row in rows], total=total, limit=limit, offset=offset
        )

    def delete(self, person_id: str) -> None:
        person = self.people.require(person_id)
        self.people.delete(person)
        self.session.commit()
