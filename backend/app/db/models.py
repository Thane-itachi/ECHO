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
from app.db.types import SealedSecret

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
    #: Legacy column, kept so old rows and admin exports keep their meaning.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Proven ownership of the address, by six-digit code. Accounts created before
    #: verification existed are grandfathered as verified by the migration.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Opt-in second factor for ordinary users: a code by email at every sign-in.
    #: Administrators never use this; their second factor is TOTP and is mandatory.
    email_otp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Set whenever the password changes, so tokens minted before it stop working.
    credentials_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


EMAIL_CODE_PURPOSES: tuple[str, ...] = ("verify_email", "login_otp", "password_reset")


class EmailCode(Base):
    """A six-digit code that proves control of an address.

    Only a keyed digest is stored. A plain SHA of six digits is a lookup table, so the
    digest is an HMAC over (address, purpose, code) with a server-side pepper: a
    dumped table cannot be reversed by hashing a million candidates.

    One row per issued code, which is also how rate limiting is counted: rows for an
    address or an IP in the last hour. No separate counter to drift out of sync.
    """

    __tablename__ = "email_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (
        CheckConstraint(f"purpose IN {_in_list(EMAIL_CODE_PURPOSES)}", name="ck_email_code_purpose"),
        # The hot query is "newest live code for this address and purpose".
        Index("ix_email_codes_lookup", "email", "purpose", "created_at"),
    )


class AdminUser(Base, Timestamped):
    """Admins live in their own table, never in `users`, and toggle on their own keys."""

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # NOT NULL on purpose: an admin without an enrolled TOTP secret cannot exist, so
    # there is no "MFA off" state to bypass. See app/admin/permissions.py.
    # Stored sealed (SealedSecret), under a system key derivation that is not any
    # user's content key: a database dump does not hand over an administrator's
    # second factor.
    mfa_secret: Mapped[str] = mapped_column(SealedSecret(), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="support_admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(f"role IN {_in_list(ADMIN_ROLES)}", name="ck_admin_users_role"),
    )


class AdminInvite(Base, Timestamped):
    """A one-time link that makes someone an administrator without us knowing a password.

    Whoever issues the link never learns the password: the person enrolling chooses it
    themselves and enrols their own TOTP secret in the same sitting. The token is stored
    hashed, so a leaked database row is not a usable invitation. Rows are single-use
    (`used_at`) and time-boxed (`expires_at`).
    """

    __tablename__ = "admin_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="founder")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issued_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(f"role IN {_in_list(ADMIN_ROLES)}", name="ck_admin_invites_role"),
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


class PushSubscription(Base, Timestamped):
    """One browser or phone that agreed to receive notifications.

    `endpoint` is the capability: whoever holds it can push to that device, so it is
    treated as a secret in transit (never logged, never returned to a client). A
    device that unsubscribes, or whose endpoint the push service retires (404/410),
    is deleted rather than kept as a dead row.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    # Browser public key (p256dh) and auth secret: needed to encrypt each payload so
    # only that device can read it. The push service relays ciphertext it cannot open.
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
