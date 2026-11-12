"""Drain the outbox: this is where the provider calls actually happen.

Kept separate from job execution so a provider outage never blocks reminder
scheduling, and so re-sending is a matter of flipping a row back to 'pending'.

Two channels today: `push` (Web Push to the user's own devices) and `email` (the same
mailer that delivers sign-in codes). A row that fails to deliver is marked `failed`
with its error, never silently dropped.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Outbox
from app.db.session import build_engine, build_session_factory
from app.repositories.system import OutboxRepository
from app.services.push import Notification, PushService, build_pusher

logger = logging.getLogger("echo.outbox")


def deliver(session: Session, entry: Outbox, *, pusher=None) -> None:
    """Hand one outbox row to its channel. Raises if the channel could not deliver."""
    if entry.channel == "push":
        if not entry.user_id:
            raise ValueError("a push notification needs a user")
        service = PushService(session, entry.user_id, pusher=pusher or build_pusher())
        payload = entry.payload or {}
        result = service.send(
            Notification(
                title=str(payload.get("title") or "ECHO"),
                body=str(payload.get("body") or "You asked to be reminded."),
                url=str(payload.get("url") or "/reminders"),
                tag=f"echo-{payload.get('reminder_id') or 'reminder'}",
                kind="reminder",
            )
        )
        if result.sent == 0 and result.failed:
            raise RuntimeError(f"push delivery failed ({', '.join(result.errors)})")
        if result.sent == 0 and result.pruned:
            # Every device had gone away. Nothing to retry.
            logger.info("no devices left for outbox entry %s", entry.id)
        return
    if entry.channel == "email":
        raise NotImplementedError("reminder email delivery is not wired yet")
    raise ValueError(f"unknown outbox channel {entry.channel!r}")


def drain(factory, *, limit: int = 50, pusher=None) -> int:
    sent = 0
    with factory() as session:
        for entry in OutboxRepository(session).pending(limit=limit):
            try:
                deliver(session, entry, pusher=pusher)
            except NotImplementedError as exc:
                # Not a failure to retry forever: the channel is not built yet.
                logger.info("outbox %s not delivered: %s", entry.id, exc)
                entry.status = "failed"
            except Exception as exc:  # noqa: BLE001 - one row must not stop the batch
                entry.status = "failed"
                logger.warning("outbox %s failed: %s", entry.id, exc)
            else:
                entry.status = "sent"
                entry.sent_at = utcnow()
                sent += 1
        session.commit()
    return sent


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    engine = build_engine()
    print(f"drained {drain(build_session_factory(engine))} notifications")
