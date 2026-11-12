"""Request/response contracts. `extra="forbid"` everywhere so a client cannot smuggle
`user_id` or any other field into a write path."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.db.models import MEMORY_CATEGORIES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_WEAK_PASSWORDS = {
    "password12",
    "password123",
    "1234567890",
    "qwertyuiop",
    "letmein123",
    "echoecho12",
}


class Category(str, Enum):
    people = "people"
    belongings = "belongings"
    work = "work"
    clients = "clients"
    documents = "documents"
    promises = "promises"
    maintenance = "maintenance"
    plans = "plans"
    events = "events"
    general = "general"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------- auth
class RegisterRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if value.lower() in _WEAK_PASSWORDS:
            raise ValueError("password is too common")
        return value


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


class AdminLoginRequest(LoginRequest):
    totp_code: str = Field(min_length=6, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------------- memories
class MemoryCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    category: Category = Category.general
    person_id: str | None = Field(default=None, max_length=36)

    @field_validator("title", "content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MemoryUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    category: Category | None = None
    person_id: str | None = Field(default=None, max_length=36)


class MemoryRead(BaseModel):
    id: str
    title: str
    content: str
    category: str
    person_id: str | None
    source: str
    confidence: float | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    items: list[MemoryRead]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------- people
class PersonCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=4_000)


class PersonRead(BaseModel):
    id: str
    name: str
    notes: str | None
    created_at: datetime


class PersonList(BaseModel):
    items: list[PersonRead]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------- proposals
class ProposalCreate(StrictModel):
    """Structured output of the extraction worker. Validated before it is stored."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    source_text: str = Field(min_length=1, max_length=20_000)
    category: Category = Category.general
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("title", "content", "source_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProposalRead(BaseModel):
    id: str
    status: str
    title: str
    content: str
    source_text: str
    category: str
    confidence: float | None
    memory_id: str | None
    created_at: datetime
    decided_at: datetime | None


class ProposalList(BaseModel):
    items: list[ProposalRead]
    total: int
    limit: int
    offset: int


class ProposalDecision(BaseModel):
    proposal: ProposalRead
    memory: MemoryRead | None = None


# ------------------------------------------------------------------- reminders
class ReminderCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    memory_id: str | None = Field(default=None, max_length=36)
    client_request_id: str | None = Field(default=None, min_length=8, max_length=120)


class ReminderRead(BaseModel):
    id: str
    title: str
    due_at: datetime
    status: str
    memory_id: str | None
    created_at: datetime


class ReminderList(BaseModel):
    items: list[ReminderRead]
    total: int
    limit: int
    offset: int


# ----------------------------------------------------------------------- admin
class PlatformStats(BaseModel):
    users_total: int
    users_active: int
    memories_total: int
    proposals_pending: int
    outbox_pending: int


class AdminUserRead(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime


class AdminUserList(BaseModel):
    items: list[AdminUserRead]
    total: int


class SetUserActiveRequest(StrictModel):
    is_active: bool


def category_values() -> list[str]:
    return list(MEMORY_CATEGORIES)


# ---------------------------------------------------------------------- links
class LinkCreate(StrictModel):
    to_memory_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(default="related", min_length=1, max_length=32)


class LinkedMemory(BaseModel):
    id: str
    title: str
    kind: str


class LinkList(BaseModel):
    items: list[LinkedMemory]


# ------------------------------------------------------------------ documents
class DocumentRead(BaseModel):
    id: str
    filename: str
    size_bytes: int
    content_type: str | None
    memory_id: str | None
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


# ----------------------------------------------------------------------- ask
class AskRequest(StrictModel):
    question: str = Field(min_length=2, max_length=2_000)


class Citation(BaseModel):
    memory_id: str
    title: str
    created_at: datetime


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    mode: str = "extractive"
    matched: int


# --------------------------------------------------------------------- capture
class CaptureRequest(StrictModel):
    text: str = Field(min_length=3, max_length=20_000)


class CaptureResponse(BaseModel):
    job_id: str
    queued: bool


# ---------------------------------------------------------------------- admin
class AdminRoleUpdate(StrictModel):
    role: str = Field(min_length=1, max_length=32)


class AdminCreateRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: str = Field(default="support_admin", min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value


class AdminAccountRead(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminAccountList(BaseModel):
    items: list[AdminAccountRead]
    total: int


class AdminAccountCreated(AdminAccountRead):
    totp_secret: str
    otpauth_url: str


class AdminEnrolmentInfo(BaseModel):
    """What a person sees before choosing a password: who this link is for, how long
    it lives, and whether it will create the account or reset an existing one."""

    email: str
    role: str
    expires_at: datetime
    account_exists: bool


class AdminEnrolmentRequest(StrictModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class AdminEnrolmentGranted(BaseModel):
    email: str
    role: str
    totp_secret: str
    otpauth_url: str
    qr_data_uri: str


class AdminEnrolmentConfirmRequest(StrictModel):
    totp_code: str = Field(min_length=6, max_length=6)


class AdminEnrolmentConfirmed(BaseModel):
    email: str
    role: str


class AdminInviteRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="support_admin", min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value


class AdminInviteIssued(BaseModel):
    """The raw token is returned exactly once, to the founder who minted it."""

    email: str
    role: str
    expires_at: datetime
    token: str
    enrol_path: str


class AdminIdentity(BaseModel):
    id: str
    email: str
    role: str
    permissions: list[str]


class HealthResponse(BaseModel):
    status: str
    database: str
    jobs_queued: int
    jobs_failed: int
    outbox_pending: int
    admins_active: int
    admins_without_recent_login: int


class AnalyticsPoint(BaseModel):
    day: str
    users: int
    memories: int
    proposals: int


class AnalyticsResponse(BaseModel):
    window_days: int
    points: list[AnalyticsPoint]
    proposals_approved: int
    proposals_rejected: int
    approval_rate: float | None


class SecurityEvent(BaseModel):
    action: str
    actor_type: str
    actor_id: str | None
    detail: dict
    created_at: datetime


class SecurityResponse(BaseModel):
    failed_admin_logins_24h: int
    failed_user_logins_24h: int
    disabled_admins: int
    inactive_users: int
    recent_events: list[SecurityEvent]


class EmergencyAccessRequest(StrictModel):
    reason: str = Field(min_length=5, max_length=500)


class EmergencyAccessResponse(BaseModel):
    access_token: str
    expires_in: int
    scope: str
