"""Serialisation helpers: decrypt at the boundary, never in the router."""
from __future__ import annotations

from app.db.models import Attachment, Memory, MemoryProposal, Person, Reminder
from app.repositories.memories import MemoryRepository, PersonRepository
from app.repositories.proposals import ProposalRepository
from app.schemas import DocumentRead, MemoryRead, PersonRead, ProposalRead, ReminderRead


def to_memory_read(memory: Memory, repo: MemoryRepository) -> MemoryRead:
    return MemoryRead(
        id=memory.id,
        title=repo.read_title(memory),
        content=repo.read_content(memory),
        category=memory.category,
        person_id=memory.person_id,
        source=memory.source,
        confidence=memory.confidence,
        archived_at=memory.archived_at,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


def to_person_read(person: Person, repo: PersonRepository | None = None) -> PersonRead:
    return PersonRead(
        id=person.id,
        name=person.name,
        notes=repo.read_notes(person) if repo is not None else None,
        created_at=person.created_at,
    )


def to_proposal_read(proposal: MemoryProposal, repo: ProposalRepository) -> ProposalRead:
    return ProposalRead(
        id=proposal.id,
        status=proposal.status,
        title=repo.read_title(proposal),
        content=repo.read_content(proposal),
        source_text=repo.read_source_text(proposal),
        category=proposal.category,
        confidence=proposal.confidence,
        memory_id=proposal.memory_id,
        created_at=proposal.created_at,
        decided_at=proposal.decided_at,
    )


def to_reminder_read(reminder: Reminder) -> ReminderRead:
    return ReminderRead(
        id=reminder.id,
        title=reminder.title,
        due_at=reminder.due_at,
        status=reminder.status,
        memory_id=reminder.memory_id,
        created_at=reminder.created_at,
    )


def to_document_read(attachment: Attachment) -> DocumentRead:
    return DocumentRead(
        id=attachment.id,
        filename=attachment.filename,
        size_bytes=attachment.size_bytes,
        content_type=attachment.content_type,
        memory_id=attachment.memory_id,
        created_at=attachment.created_at,
    )
