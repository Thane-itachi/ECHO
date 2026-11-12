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
