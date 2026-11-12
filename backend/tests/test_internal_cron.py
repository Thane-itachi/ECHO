"""The scheduler endpoints: the worker's loop and the migration, behind a secret.

A serverless deploy has no long-running worker, so the loop became `POST /api/internal/tick`
and the migration became `POST /api/internal/migrate`. Both are public URLs, so the
interesting assertions are about who may call them: no secret configured means the door
is shut, and a wrong secret is refused without telling you which part was wrong.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import Job, Outbox, PushSubscription, Reminder

SECRET = "cron-secret-for-tests-0123456789"


@pytest.fixture()
def cron(monkeypatch):
    """Configure a secret for the endpoints, the way a deployment would."""
    import app.api.routes_internal as routes_internal

    configured = replace(settings, cron_secret=SECRET)
    monkeypatch.setattr(routes_internal, "settings", configured)
    return configured


@pytest.fixture()
def no_secret(monkeypatch):
    import app.api.routes_internal as routes_internal

    monkeypatch.setattr(routes_internal, "settings", replace(settings, cron_secret=None))


def auth(secret: str = SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def test_without_a_configured_secret_the_endpoints_refuse_to_run(client, no_secret):
    for path in ("/api/internal/tick", "/api/internal/migrate"):
        response = client.post(path, headers=auth("anything"))
        assert response.status_code == 403
        assert "not set" in response.text


def test_a_wrong_or_missing_secret_is_refused(client, cron):
    assert client.post("/api/internal/tick").status_code == 403
    assert client.post("/api/internal/tick", headers=auth("guess")).status_code == 403
    assert client.post("/api/internal/migrate", headers=auth("guess")).status_code == 403


def test_the_secret_is_compared_whole(client, cron):
    # A prefix is not a match, and the response says nothing about how close it was.
    assert client.post("/api/internal/tick", headers=auth(SECRET[:-1])).status_code == 403


def test_a_tick_delivers_a_due_reminder(client, session_factory, cron, push_keys, pusher):
    """One call does what the worker loop did: claim the job, then drain the outbox."""
    from tests.support import sign_in

    headers = sign_in(client, email="ticker@example.com")
    subscribed = client.post(
        "/api/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/tick-test",
            "keys": {"p256dh": "BOrTLk9vExampleKeyMaterial", "auth": "authSecretValue"},
        },
        headers=headers,
    )
    assert subscribed.status_code == 201, subscribed.text
    # The API refuses a reminder in the past, so it is created a moment out and then
    # moved into the past: this is the state the scheduler finds after a quiet hour.
    reminder = client.post(
        "/api/reminders",
        json={"title": "Water the plants", "due_at": (utcnow() + timedelta(seconds=30)).isoformat()},
        headers=headers,
    )
    assert reminder.status_code == 201, reminder.text
    due = utcnow() - timedelta(minutes=1)
    with session_factory() as session:
        session.query(Reminder).update({"due_at": due})
        session.query(Job).update({"run_at": due})
        session.commit()

    tick = client.post("/api/internal/tick", headers=auth())
    assert tick.status_code == 200, tick.text
    assert tick.json()["claimed"] >= 1
    assert tick.json()["delivered"] >= 1
    assert pusher.sent, "a due reminder should have reached the subscribed device"

    with session_factory() as session:
        job = session.query(Job).filter(Job.kind == "reminder.notify").one()
        assert job.status == "done"
        row = session.query(Outbox).filter(Outbox.channel == "push").one()
        assert row.status == "sent"
        assert session.query(Reminder).one().status == "notified"


def test_a_tick_with_nothing_to_do_is_a_no_op_not_an_error(client, cron, session_factory):
    tick = client.post("/api/internal/tick", headers=auth())
    assert tick.status_code == 200
    assert tick.json() == {"claimed": 0, "delivered": 0}
    with session_factory() as session:
        assert session.query(PushSubscription).count() == 0


def test_the_migration_endpoint_runs_alembic_upgrade_head(client, cron, monkeypatch):
    calls = []

    import alembic.command as alembic_command

    monkeypatch.setattr(alembic_command, "upgrade", lambda config, rev: calls.append((config, rev)))

    response = client.post("/api/internal/migrate", headers=auth())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(calls) == 1
    config, revision = calls[0]
    assert revision == "head"
    # The script location must point at the real migrations, or "upgrade head" is a no-op.
    assert config.get_main_option("script_location").endswith("migrations")


def test_a_failed_migration_reports_why(client, cron):
    """The operator holding the secret gets the reason, not "internal server error"."""
    headers = auth()

    from alembic import command

    def explode(config, revision, **kwargs):  # noqa: ANN001
        raise RuntimeError("psycopg.OperationalError: could not translate host name")

    original = command.upgrade
    command.upgrade = explode  # alembic calls it as a module-level function
    try:
        response = client.post("/api/internal/migrate", headers=headers)
    finally:
        command.upgrade = original

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "migration_failed"
    assert "could not translate host name" in body["message"]


def test_the_migration_finds_its_files_in_the_deployed_layout():
    """`/var/task/backend` in a bundle, `backend/` locally: the root is the file's grandparent.

    This was wrong once (parents[3]), and the only symptom was a 500 from a deploy saying
    "Path doesn't exist: /var/task/migrations". Asserting the two files the migration needs
    costs a millisecond.
    """
    from app.api.routes_internal import BACKEND_ROOT

    assert (BACKEND_ROOT / "alembic.ini").is_file()
    assert (BACKEND_ROOT / "migrations" / "env.py").is_file()


def test_the_operator_can_see_what_the_delivery_layer_did(client, cron, session_factory):
    """A skipped message must be legible as a deliberate skip, not as a mystery."""
    from tests.support import sign_in

    headers = sign_in(client, email="outbox-reader@example.com")
    reminder = client.post(
        "/api/reminders",
        json={"title": "Sign the delivery note", "due_at": (utcnow() + timedelta(seconds=30)).isoformat()},
        headers=headers,
    )
    assert reminder.status_code == 201, reminder.text

    due = utcnow() - timedelta(minutes=1)
    with session_factory() as session:
        session.query(Reminder).update({"due_at": due})
        session.query(Job).update({"run_at": due})
        session.commit()

    assert client.post("/api/internal/tick", headers=auth()).status_code == 200

    response = client.get("/api/internal/outbox", headers=auth())
    assert response.status_code == 200
    items = response.json()["items"]
    assert items, "the reminder should have left an outbox row"
    assert {"channel", "status", "attempts", "last_error"} <= set(items[0])
    assert items[0]["status"] in {"sent", "suppressed", "pending", "failed"}
    # No provider in the test environment: the skip is recorded with its reason.
    assert items[0]["status"] in {"sent", "suppressed"}


def test_the_outbox_view_needs_the_secret(client):
    assert client.get("/api/internal/outbox").status_code == 403
