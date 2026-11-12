"""Reminder email: the message, the way out of it, and what happens when it fails.

The provider is a transport, so it is replaced by `CapturingMailer` (the suite-wide
fixture). What is asserted here is ECHO's own behaviour: that a reminder produces one
email, that the template carries a working opt-out link, that the link cannot be
pointed at somebody else's account, that one click does not unsubscribe anyone, and
that a failing provider is retried rather than quietly dropping the reminder.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import Job, Outbox, User
from app.scripts.drain_outbox import MAX_ATTEMPTS, Suppressed, drain
from app.services import reminder_email
from app.services.jobs import enqueue_outbox
from app.scripts.drain_outbox import deliver
from app.services.mailer import MailError
from app.services.reminder_email import token_for, user_id_from_token
from app.worker import handle_reminder_notify
from tests.support import sign_in


class FlakyMailer:
    """Fails a given number of times, then succeeds. Stands in for a provider outage."""

    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.attempts = 0
        self.sent = []

    def send(self, message) -> None:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise MailError("the mail provider is having a moment")
        self.sent.append(message)


@pytest.fixture()
def email_on(monkeypatch):
    """Pretend a provider is configured, so a reminder is meant to be delivered.

    The module reads `settings` at call time, so patching that object is enough; the
    transport itself stays the in-memory capture.
    """
    import app.scripts.drain_outbox as drain_module

    adjusted = replace(
        settings,
        email_provider="resend",
        resend_api_key="test-key",
        public_app_url="http://echo.test",
        public_api_url="http://api.echo.test",
    )
    monkeypatch.setattr(drain_module, "settings", adjusted, raising=False)
    monkeypatch.setattr("app.core.config.settings", adjusted, raising=False)
    monkeypatch.setattr("app.services.reminder_email.settings", adjusted, raising=False)
    return adjusted


def a_user(session, email: str = "reader@example.com", *, enabled: bool = True) -> User:
    user = User(email=email, password_hash="x", email_verified=True, reminder_email_enabled=enabled)
    session.add(user)
    session.commit()
    return user


def a_reminder(session, user: User, title: str = "Call the plumber"):
    from app.db.models import Reminder

    reminder = Reminder(
        user_id=user.id,
        title=title,
        due_at=utcnow() + timedelta(minutes=1),
        status="scheduled",
        notification_key=f"reminder:{user.id}:{title}",
    )
    session.add(reminder)
    session.commit()
    return reminder


def a_job_for(session, reminder) -> Job:
    job = Job(kind="reminder.notify", payload={"reminder_id": reminder.id}, status="running", run_at=utcnow())
    session.add(job)
    session.commit()
    return job


# --- the message -------------------------------------------------------------------


def test_the_email_says_what_is_due_and_how_to_stop_it(session_factory, email_on, mailer):
    with session_factory() as session:
        user = a_user(session)
        build = reminder_email.build_message(
            user, {"title": "Return John's laptop", "due_at": "2026-11-12T09:00:00"}
        )

    assert build.to == "reader@example.com"
    assert build.subject == "Reminder: Return John's laptop"
    assert "Due Thu 12 Nov 2026, 09:00 UTC" in build.text
    assert "Return John's laptop" in build.text
    # The opt-out is a real, absolute link, and it is offered in the footer and header.
    assert build.text.count("/api/reminders/email/opt-out?token=") == 1
    assert "List-Unsubscribe" in build.headers
    assert build.html and "Return John&#x27;s laptop".replace("&#x27;", "'") in build.html.replace("'", "'")


def test_a_long_title_is_folded_not_dumped_whole(session_factory, email_on, mailer):
    with session_factory() as session:
        user = a_user(session)
        build = reminder_email.build_message(user, {"title": "word " * 100, "due_at": None})
    assert len(build.subject) < 160
    assert build.subject.endswith("…") or build.subject.count("word") < 100


def test_an_opt_out_link_only_works_for_the_account_it_names(email_on):
    token = token_for("user-a")
    assert user_id_from_token(token) == "user-a"
    # Point the same signature at another account: it no longer verifies.
    forged = token.replace("user-a", "user-b", 1)
    with pytest.raises(reminder_email.BadToken):
        user_id_from_token(forged)
    with pytest.raises(reminder_email.BadToken):
        user_id_from_token("no-dot-here")
    with pytest.raises(reminder_email.BadToken):
        user_id_from_token("")


# --- the page in the email ----------------------------------------------------------


def test_the_link_asks_before_it_unsubscribes(client, session_factory, email_on):
    with session_factory() as session:
        user = a_user(session)
        token = token_for(user.id)

    page = client.get(f"/api/reminders/email/opt-out?token={token}")
    assert page.status_code == 200
    assert "Turn off reminder emails?" in page.text

    # Opening the page (which is all a mail scanner does) changes nothing.
    with session_factory() as session:
        assert session.get(User, user.id).reminder_email_enabled is True

    applied = client.post(
        "/api/reminders/email/opt-out", data={"token": token, "action": "off"}, follow_redirects=False
    )
    assert applied.status_code == 200
    assert "Reminder emails are off" in applied.text
    with session_factory() as session:
        assert session.get(User, user.id).reminder_email_enabled is False


def test_the_same_page_turns_them_back_on(client, session_factory, email_on):
    with session_factory() as session:
        user = a_user(session, enabled=False)
        token = token_for(user.id)

    assert "already off" in client.get(f"/api/reminders/email/opt-out?token={token}").text
    back_on = client.post("/api/reminders/email/opt-out", data={"token": token, "action": "on"})
    assert "back on" in back_on.text
    with session_factory() as session:
        assert session.get(User, user.id).reminder_email_enabled is True


def test_a_forged_or_stale_link_is_refused_without_leaking_anything(client, session_factory, email_on):
    with session_factory() as session:
        user = a_user(session)
        good = token_for(user.id)

    for bad in ("", "nonsense", good[:-2] + "ff"):
        response = client.get(f"/api/reminders/email/opt-out?token={bad}")
        assert response.status_code == 404
        assert "reader@example.com" not in response.text
    with session_factory() as session:
        assert session.get(User, user.id).reminder_email_enabled is True


def test_the_switch_in_the_app_does_the_same_thing(client, session_factory):
    headers = sign_in(client, email="switcher@example.com")
    assert client.get("/api/auth/me", headers=headers).json()["reminder_email_enabled"] is True

    off = client.patch("/api/auth/reminder-email", json={"enabled": False}, headers=headers)
    assert off.status_code == 200
    assert off.json()["reminder_email_enabled"] is False
    with session_factory() as session:
        user = session.scalars(select(User).where(User.email == "switcher@example.com")).one()
        assert user.reminder_email_enabled is False


# --- who gets queued ----------------------------------------------------------------


def test_a_reminder_queues_email_only_when_the_account_wants_it(session_factory, email_on):
    with session_factory() as session:
        wanted = a_user(session, "wants@example.com")
        declined = a_user(session, "declined@example.com", enabled=False)
        handle_reminder_notify(session, a_job_for(session, a_reminder(session, wanted)))
        handle_reminder_notify(session, a_job_for(session, a_reminder(session, declined, "Pay the rent")))
        session.commit()

        rows = list(session.scalars(select(Outbox).where(Outbox.channel == "email")))
        assert len(rows) == 1
        assert rows[0].user_id == wanted.id


# --- delivery -----------------------------------------------------------------------


def test_draining_sends_the_reminder_and_marks_it_sent(session_factory, email_on, mailer):
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:one",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r1", "title": "Renew the insurance", "due_at": "2026-11-12T09:00:00"},
        )
        session.commit()

    assert drain(session_factory, mailer=mailer) == 1
    sent = mailer.last("reader@example.com")
    assert sent is not None and "Renew the insurance" in sent.text
    with session_factory() as session:
        row = session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:one")).one()
        assert row.status == "sent" and row.sent_at is not None and row.last_error is None


def test_an_opt_out_between_firing_and_delivery_is_still_honoured(session_factory, email_on, mailer):
    """The window is real: a reminder can sit in the outbox for a while."""
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:two",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r2", "title": "Water the plants"},
        )
        user.reminder_email_enabled = False
        session.commit()

    assert drain(session_factory, mailer=mailer) == 0
    assert mailer.last("reader@example.com") is None
    with session_factory() as session:
        row = session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:two")).one()
        assert row.status == "suppressed"
        assert "turned off" in (row.last_error or "")


def test_a_deleted_account_takes_its_unsent_reminders_with_it(session_factory, email_on, mailer):
    """Deleting an account cascades to its outbox: an orphan cannot be delivered, and
    keeping it would be a phone number's worth of stale promise."""
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:three",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r3", "title": "Anything"},
        )
        session.commit()
        session.delete(session.get(User, user.id))
        session.commit()

    assert drain(session_factory, mailer=mailer) == 0
    assert mailer.last("reader@example.com") is None
    with session_factory() as session:
        assert session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:three")).one_or_none() is None


def test_a_row_whose_account_vanished_is_suppressed_not_retried(session_factory, email_on, mailer):
    """Foreign keys make this unreachable in practice, which is why it is asserted
    directly: the drain must decline, not crash, if it is ever handed a dead account."""
    with session_factory() as session:
        entry = Outbox(user_id="a-user-who-is-not-there", channel="email", payload={"title": "Nobody home"})
        with pytest.raises(Suppressed):
            deliver(session, entry, mailer=mailer)
    assert mailer.last() is None


def test_a_provider_outage_retries_with_backoff_then_gives_up(session_factory, email_on):
    mailer = FlakyMailer(failures=99)
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:four",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r4", "title": "Something timely"},
        )
        session.commit()

    for expected in range(1, MAX_ATTEMPTS + 1):
        drain(session_factory, mailer=mailer)
        with session_factory() as session:
            row = session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:four")).one()
            assert row.attempts == expected
            if expected < MAX_ATTEMPTS:
                # Still pending, and not due again until the backoff has passed.
                assert row.status == "pending"
                assert row.available_at is not None and row.available_at > utcnow()
                # Pretend the delay elapsed, which is what the next pass would see.
                row.available_at = None
                session.commit()
            else:
                assert row.status == "failed"
                assert "having a moment" in (row.last_error or "")

    # The backoff is real: a second drain in the same moment does not try again early.
    before = mailer.attempts
    drain(session_factory, mailer=mailer)
    assert mailer.attempts == before


def test_a_transient_failure_is_retried_and_then_delivered(session_factory, email_on):
    mailer = FlakyMailer(failures=1)
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:five",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r5", "title": "Second time lucky"},
        )
        session.commit()

    assert drain(session_factory, mailer=mailer) == 0
    with session_factory() as session:
        row = session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:five")).one()
        assert row.status == "pending" and row.attempts == 1
        # Pretend the backoff has passed.
        row.available_at = None
        session.commit()

    assert drain(session_factory, mailer=mailer) == 1
    assert mailer.sent and "Second time lucky" in mailer.sent[0].text


def test_nothing_is_delivered_when_no_provider_is_configured(session_factory, mailer, caplog):
    """Development has no provider. The row says so instead of claiming a send, and the
    message goes to the log so the template can still be walked."""
    with session_factory() as session:
        user = a_user(session)
        enqueue_outbox(
            session,
            idempotency_key="outbox:six",
            channel="email",
            user_id=user.id,
            payload={"reminder_id": "r6", "title": "Nothing to send with"},
        )
        session.commit()

    with caplog.at_level("WARNING", logger="echo.mail"):
        assert drain(session_factory, mailer=mailer) == 0
    assert mailer.last("reader@example.com") is None
    assert "Nothing to send with" in caplog.text  # logged, not sent
    with session_factory() as session:
        row = session.scalars(select(Outbox).where(Outbox.idempotency_key == "outbox:six")).one()
        assert row.status == "suppressed"
        assert "no mail provider" in (row.last_error or "")
