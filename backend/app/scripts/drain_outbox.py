"""Drain the outbox: this is where the provider calls actually happen.

Kept separate from job execution so a provider outage never blocks reminder
scheduling, and so re-sending is a matter of flipping a row back to 'pending'.

Two channels today: `push` (Web Push to the user's own devices) and `email` (the same
mailer that delivers sign-in codes). A row is only ever in one of four states when the
drain lets go of it:

* `sent` — the provider accepted it.
* `pending` — a transient failure; it will be tried again after a backoff.
* `failed` — it kept failing, or the provider refused it. Someone should look.
* `suppressed` — deliberately not sent: reminder email is off, or the account is gone.
  Not a failure, and never retried, so an opt-out does not look like an outage.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Outbox, User
from app.db.session import build_engine, build_session_factory
from app.repositories.system import OutboxRepository
from app.services import reminder_email
from app.services.mailer import LogMailer, Mailer, build_mailer
from app.services.push import Notification, PushService, build_pusher

logger = logging.getLogger("echo.outbox")

#: A reminder is time-sensitive, so this is not an infinite retry ladder: five
#: attempts over roughly half an hour. After that the message is stale anyway.
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 900


class Suppressed(RuntimeError):
    """The recipient should not receive this. Terminal, and not a failure."""


def _backoff(attempts: int) -> timedelta:
    seconds = min(BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), BACKOFF_MAX_SECONDS)
    return timedelta(seconds=seconds)


def _deliver_email(session: Session, entry: Outbox, *, mailer: Mailer | None = None) -> None:
    from app.core.config import settings

    user = session.get(User, entry.user_id) if entry.user_id else None
    if user is None or not user.is_active:
        raise Suppressed("the account behind this reminder is gone")
    # Checked again here, not only when the reminder fired: between the two an hour
    # can pass, and an opt-out that only applies to future reminders is not an opt-out.
    if not user.reminder_email_enabled:
        raise Suppressed("reminder email is turned off for this account")
    if not user.email:
        raise Suppressed("the account has no address")
    message = reminder_email.build_message(user, entry.payload or {})
    if not settings.email_enabled:
        # Nothing can actually be delivered. The row says so, and in development the
        # message is written to the log so the template and the opt-out link can be
        # walked without a provider. It is never called "sent".
        if not settings.is_production:
            LogMailer().send(message)
            raise Suppressed("no mail provider configured: the message went to the log, not to an inbox")
        raise Suppressed("no mail provider is configured, so nothing can be delivered")
    (mailer or build_mailer()).send(message)


def deliver(session: Session, entry: Outbox, *, pusher=None, mailer=None) -> None:
    """Hand one outbox row to its channel. Raises if the channel could not deliver."""
    if entry.channel == "push":
        if not entry.user_id:
            raise Suppressed("a push notification needs a user")
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
            raise Suppressed("every device for this account had been retired")
        return
    if entry.channel == "email":
        _deliver_email(session, entry, mailer=mailer)
        return
    raise Suppressed(f"unknown outbox channel {entry.channel!r}")


def drain(factory, *, limit: int = 50, pusher=None, mailer=None) -> int:
    sent = 0
    with factory() as session:
        for entry in OutboxRepository(session).pending(limit=limit):
            try:
                deliver(session, entry, pusher=pusher, mailer=mailer)
            except Suppressed as exc:
                entry.status = "suppressed"
                entry.last_error = str(exc)[:2000]
                logger.info("outbox %s suppressed: %s", entry.id, exc)
            except Exception as exc:  # noqa: BLE001 - one row must not stop the batch
                entry.attempts = (entry.attempts or 0) + 1
                entry.last_error = str(exc)[:2000]
                if entry.attempts >= MAX_ATTEMPTS:
                    entry.status = "failed"
                    logger.warning("outbox %s failed after %s attempts: %s", entry.id, entry.attempts, exc)
                else:
                    entry.available_at = utcnow() + _backoff(entry.attempts)
                    logger.warning(
                        "outbox %s attempt %s failed, retrying after %s: %s",
                        entry.id,
                        entry.attempts,
                        entry.available_at,
                        exc,
                    )
            else:
                entry.status = "sent"
                entry.sent_at = utcnow()
                entry.last_error = None
                sent += 1
        session.commit()
    return sent


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    engine = build_engine()
    print(f"drained {drain(build_session_factory(engine))} notifications")
