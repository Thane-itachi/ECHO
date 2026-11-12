"""Time helpers.

Every timestamp column stores *naive UTC*. SQLite and PostgreSQL then behave the
same way and there is no tz round-trip drift (SQLite silently drops tzinfo, which
is how "same night" comparisons quietly go wrong later). Convert to local time at
the edge, never in storage.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Normalise an incoming datetime to naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
