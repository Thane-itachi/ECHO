"""Drain the outbox: this is where a real email/push provider call goes.

Kept separate from job execution so a provider outage never blocks reminder
scheduling, and so re-sending is a matter of flipping a row back to 'pending'.
"""
from __future__ import annotations

import logging

from app.core.time import utcnow
from app.db.models import Outbox
from app.db.session import build_engine, build_session_factory
from app.repositories.system import OutboxRepository

logger = logging.getLogger("echo.outbox")


def deliver(entry: Outbox) -> None:
    """Replace with the real transport (email/push). Idempotent by key at the provider."""
    logger.info("delivering %s to user=%s payload=%s", entry.channel, entry.user_id, entry.payload)


def drain(factory, *, limit: int = 50) -> int:
    sent = 0
    with factory() as session:
        for entry in OutboxRepository(session).pending(limit=limit):
            deliver(entry)
            entry.status = "sent"
            entry.sent_at = utcnow()
            sent += 1
        session.commit()
    return sent


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    engine = build_engine()
    print(f"drained {drain(build_session_factory(engine))} notifications")
