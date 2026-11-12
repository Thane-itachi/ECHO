"""ECHO data model.

Ownership rule (fix #1 from the review): every private table carries a real,
NOT NULL `user_id` column. There is no "verified through the parent record"
ownership anywhere, so no query can accidentally reach another tenant's row.

Every datetimes is naive UTC (see app/core/time.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time import utcnow

MEMORY_CATEGORIES: tuple[str, ...] = (
    "people",
    "belongings",
    "work",
    "clients",
    "documents",
    "promises",
    "maintenance",
    "plans",
    "events",
    "general",
)
MEMORY_SOURCES: tuple[str, ...] = ("user", "ai_extraction", "import")
ADMIN_ROLES: tuple[str, ...] = ("founder", "platform_admin", "support_admin")
DOCUMENT_SCAN_STATUSES: tuple[str, ...] = ("stored", "quarantined")
PROPOSAL_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")
JOB_STATUSES: tuple[str, ...] = ("queued", "running", "done", "failed")
OUTBOX_STATUSES: tuple[str, ...] = ("pending", "sent", "failed")
REMINDER_STATUSES: tuple[str, ...] = ("scheduled", "notified", "cancelled", "done")
ACTOR_TYPES: tuple[str, ...] = ("user", "admin", "system")


def _in_list(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(Base, Timestamped):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AdminUser(Base, Timestamped):
    """Admins live in their own table, never in `users`, and toggle on their own keys."""

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # NOT NULL on purpose: an admin without an enrolled TOTP secret cannot exist, so
    # there is no "MFA off" state to bypass. See app/admin/permissions.py.
    mfa_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="support_admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(f"role IN {_in_list(ADMIN_ROLES)}", name="ck_admin_users_role"),
    )


class Person(Base, Timestamped):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The name stays readable: it is a label used for pickers, sorting and reminder
    # text, not the substance of what a user told ECHO. Notes are encrypted.
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    notes_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_index: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Memory(Base, Timestamped):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title_enc: Mapped[str] = mapped_column(Text, nullable=False)
    content_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # Blind index over title + content: keyed HMAC tokens, never the words themselves.
    search_index: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(f"category IN {_in_list(MEMORY_CATEGORIES)}", name="ck_memories_category"),
        CheckConstraint(f"source IN {_in_list(MEMORY_SOURCES)}", name="ck_memories_source"),
        Index("ix_memories_user_created", "user_id", "created_at"),
    )


class Relationship(Base, Timestamped):
    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    to_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="related")

    __table_args__ = (UniqueConstraint("from_memory_id", "to_memory_id", "kind", name="uq_relationship"),)


class Attachment(Base, Timestamped):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Reminder(Base, Timestamped):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    # Stable per-occurrence key: the unit of "send this exactly once".
    notification_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Client-supplied idempotency key for safe retries of the create call itself.
    client_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {_in_list(REMINDER_STATUSES)}", name="ck_reminders_status"),
        UniqueConstraint("user_id", "client_request_id", name="uq_reminders_client_request"),
    )


class MemoryProposal(Base, Timestamped):
    """AI extraction output. Never becomes a memory without an explicit approval."""

    __tablename__ = "memory_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    title_enc: Mapped[str] = mapped_column(Text, nullable=False)
    content_enc: Mapped[str] = mapped_column(Text, nullable=False)
    source_text_enc: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {_in_list(PROPOSAL_STATUSES)}", name="ck_proposals_status"),
        Index("ix_proposals_user_status", "user_id", "status"),
    )


class Job(Base, Timestamped):
    """Durable work queue. Claimed with SKIP LOCKED on PostgreSQL, never in-process."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {_in_list(JOB_STATUSES)}", name="ck_jobs_status"),
        Index("ix_jobs_claim", "status", "run_at"),
    )


class Outbox(Base, Timestamped):
    """Notifications are written here first, then delivered by a separate drain."""

    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (CheckConstraint(f"status IN {_in_list(OUTBOX_STATUSES)}", name="ck_outbox_status"),)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (CheckConstraint(f"actor_type IN {_in_list(ACTOR_TYPES)}", name="ck_audit_actor_type"),)
