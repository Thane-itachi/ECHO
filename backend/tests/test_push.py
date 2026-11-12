"""Web Push: subscriptions, delivery, and the ways a device goes away.

The push service is a transport, so it is faked here (`CapturingPusher`). What is
actually asserted is ECHO's own logic: who may subscribe, that an endpoint cannot stay
attached to a previous account, that a retired endpoint is deleted instead of retried,
and that one broken device never stops the others from being notified.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import Job, Outbox, PushSubscription
from app.services.push import (
    MAX_FAILURES,
    CapturingPusher,
    Notification,
    PushNotConfigured,
    PushService,
    build_pusher,
)

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"


def a_subscription(endpoint: str = ENDPOINT, **overrides) -> dict:
    payload = {
        "endpoint": endpoint,
        "keys": {"p256dh": "BOrTLk9vExampleKeyMaterial", "auth": "authSecretValue"},
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def pusher(app):
    """Swap the transport for the duration of a test: nothing dials out."""
    capture = CapturingPusher()
    app.state.pusher = capture
    return capture


@pytest.fixture()
def push_keys(monkeypatch):
    """Pretend a VAPID keypair is configured, without touching the real env.

    Settings are frozen, so the replacement is installed in the modules that read
    them (`app.api.routes_push` for the public key endpoint, `app.services.push` for
    the transport).
    """
    import app.api.routes_push as routes_push
    import app.services.push as push_module
    from app.scripts.vapid_keys import generate

    # A real keypair, so the startup check on the pair runs exactly as in production.
    public_key, private_key = generate()
    adjusted = replace(settings, vapid_public_key=public_key, vapid_private_key=private_key)
    monkeypatch.setattr(routes_push, "settings", adjusted)
    monkeypatch.setattr(push_module, "settings", adjusted)
    return adjusted


def test_no_keypair_means_nobody_subscribes(client, make_user):
    user = make_user()
    assert client.get("/api/push/key").json() == {"enabled": False, "public_key": None}
    refused = client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "push_not_configured"


def test_subscribing_registers_the_device(client, make_user, push_keys, pusher):  # noqa: D401
    user = make_user()

    key = client.get("/api/push/key").json()
    assert key == {"enabled": True, "public_key": push_keys.vapid_public_key}

    created = client.post(
        "/api/push/subscribe",
        json=a_subscription(),
        headers={**user["headers"], "User-Agent": IPHONE},
    )
    assert created.status_code == 201, created.text
    assert created.json()["label"] == "iPhone"
    assert created.json()["count"] == 1

    listed = client.get("/api/push/subscriptions", headers=user["headers"]).json()
    assert listed["count"] == 1
    # The endpoint is a capability: it must never come back out of the API.
    assert ENDPOINT not in str(listed)


def test_resubscribing_the_same_browser_does_not_duplicate_it(client, make_user, push_keys, pusher, session_factory):
    user = make_user()
    for _ in range(3):
        client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    with session_factory() as session:
        rows = session.scalars(select(PushSubscription)).all()
    assert len(rows) == 1


def test_a_device_that_changes_hands_moves_to_the_new_account(client, make_user, push_keys, pusher, session_factory):
    first, second = make_user(), make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=first["headers"])
    client.post("/api/push/subscribe", json=a_subscription(), headers=second["headers"])

    with session_factory() as session:
        row = session.scalars(select(PushSubscription)).one()
        assert row.user_id == second["id"]

    # The first account lost the device, so it must not be able to notify it.
    assert client.get("/api/push/subscriptions", headers=first["headers"]).json()["count"] == 0
    assert client.post("/api/push/test", headers=first["headers"]).status_code == 404


def test_a_bad_subscription_is_refused(client, make_user, push_keys, pusher):
    user = make_user()
    for broken in (
        a_subscription(endpoint="http://insecure.example/push"),
        a_subscription(keys={"p256dh": "", "auth": "x"}),
        a_subscription(keys={"p256dh": "x", "auth": ""}),
        a_subscription(endpoint="https://example.com/" + "a" * 600),
    ):
        response = client.post("/api/push/subscribe", json=broken, headers=user["headers"])
        assert response.status_code == 422, broken


def test_unsubscribing_is_idempotent(client, make_user, push_keys, pusher):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    first = client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}, headers=user["headers"])
    second = client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}, headers=user["headers"])
    assert first.json() == {"removed": True, "count": 0}
    assert second.json() == {"removed": False, "count": 0}


def test_another_users_endpoint_cannot_be_unsubscribed(client, make_user, push_keys, pusher):
    owner, stranger = make_user(), make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=owner["headers"])
    response = client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}, headers=stranger["headers"])
    assert response.json() == {"removed": False, "count": 0}
    assert client.get("/api/push/subscriptions", headers=owner["headers"]).json()["count"] == 1


def test_test_notification_reaches_every_device(client, make_user, push_keys, pusher):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription("https://fcm.example/one"), headers=user["headers"])
    client.post("/api/push/subscribe", json=a_subscription("https://fcm.example/two"), headers=user["headers"])

    response = client.post("/api/push/test", headers=user["headers"])
    assert response.json() == {"attempted": 2, "sent": 2, "pruned": 0, "failed": 0}
    payload = pusher.payloads()[0]
    assert payload["title"] == "ECHO is listening"
    assert payload["url"] == "/reminders"


def test_the_notification_never_carries_an_endpoint(client, make_user, push_keys, pusher):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    client.post("/api/push/test", headers=user["headers"])
    for payload in pusher.payloads():
        assert ENDPOINT not in str(payload)


def test_a_retired_device_is_deleted_not_retried(client, make_user, push_keys, pusher, session_factory):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    pusher.fail_status = 410

    response = client.post("/api/push/test", headers=user["headers"])
    assert response.json() == {"attempted": 1, "sent": 0, "pruned": 1, "failed": 0}
    with session_factory() as session:
        assert session.scalars(select(PushSubscription)).all() == []


def test_a_failing_device_is_kept_until_it_is_hopeless(client, make_user, push_keys, pusher, session_factory):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    pusher.fail_status = 500

    first = client.post("/api/push/test", headers=user["headers"]).json()
    assert first["failed"] == 1 and first["pruned"] == 0
    with session_factory() as session:
        assert session.scalars(select(PushSubscription)).one().failure_count == 1

    for _ in range(MAX_FAILURES):
        client.post("/api/push/test", headers=user["headers"])
    with session_factory() as session:
        assert session.scalars(select(PushSubscription)).all() == []


def test_a_success_clears_the_failure_count(client, make_user, push_keys, pusher, session_factory):
    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    pusher.fail_status = 500
    client.post("/api/push/test", headers=user["headers"])
    pusher.fail_status = None
    client.post("/api/push/test", headers=user["headers"])
    with session_factory() as session:
        row = session.scalars(select(PushSubscription)).one()
        assert row.failure_count == 0
        assert row.last_success_at is not None


def test_one_broken_device_does_not_stop_the_others(session_factory, app):
    """The transport fails per device, so a single dead endpoint cannot mute the rest."""

    class HalfBroken(CapturingPusher):
        def send(self, subscription, payload):
            if subscription.endpoint.endswith("broken"):
                raise RuntimeError("boom")
            super().send(subscription, payload)

    with session_factory() as session:
        from app.db.models import User
        from app.core.security import hash_password

        user = User(email="multi@example.com", password_hash=hash_password("correct-horse-battery"))
        session.add(user)
        session.commit()
        for suffix in ("broken", "healthy"):
            session.add(
                PushSubscription(
                    user_id=user.id,
                    endpoint=f"https://fcm.example/{suffix}",
                    p256dh="key",
                    auth="auth",
                )
            )
        session.commit()

        service = PushService(session, user.id, pusher=HalfBroken())
        result = service.send(Notification(title="t", body="b"))
        session.commit()

    assert (result.sent, result.failed, result.pruned) == (1, 1, 0)


def test_a_reminder_queues_a_push_only_when_a_device_exists(client, make_user, session_factory, push_keys, pusher):
    from app.worker import handle_reminder_notify

    user = make_user()
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    client.post("/api/reminders", json={"title": "renew the passport", "due_at": due}, headers=user["headers"])

    # No device yet: the reminder queues its email row and nothing else.
    with session_factory() as session:
        job = session.scalars(select(Job).where(Job.kind == "reminder.notify")).one()
        handle_reminder_notify(session, job)
        session.commit()
        channels = [row.channel for row in session.scalars(select(Outbox)).all()]
    assert channels == ["email"]

    # A second reminder, this time with the phone subscribed.
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    second = client.post(
        "/api/reminders", json={"title": "call the plumber", "due_at": soon}, headers=user["headers"]
    ).json()
    with session_factory() as session:
        # The job for the second reminder, which is the one that has a phone to reach.
        job = session.scalars(
            select(Job).where(Job.payload["reminder_id"].as_string() == second["id"])
        ).one()
        handle_reminder_notify(session, job)
        session.commit()
        channels = [row.channel for row in session.scalars(select(Outbox)).all()]
    assert sorted(channels) == ["email", "email", "push"]


def test_draining_the_outbox_actually_pushes(client, make_user, session_factory, push_keys, pusher):
    from app.scripts.drain_outbox import drain

    user = make_user()
    client.post("/api/push/subscribe", json=a_subscription(), headers=user["headers"])
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    reminder = client.post(
        "/api/reminders", json={"title": "water the plants", "due_at": due}, headers=user["headers"]
    ).json()

    from app.worker import handle_reminder_notify

    with session_factory() as session:
        job = session.scalars(select(Job).where(Job.kind == "reminder.notify")).one()
        handle_reminder_notify(session, job)
        session.commit()

    sent = drain(session_factory, pusher=pusher)
    assert sent == 1  # the push row; the email row is not wired yet
    titles = [payload["title"] for payload in pusher.payloads()]
    assert reminder["title"] in titles

    with session_factory() as session:
        statuses = {row.channel: row.status for row in session.scalars(select(Outbox)).all()}
    assert statuses["push"] == "sent"


def test_no_keypair_means_no_sending(app, session_factory):
    """A deployment without VAPID keys must not believe it delivered anything."""
    with session_factory() as session:
        from app.core.security import hash_password
        from app.db.models import User

        user = User(email="nokeys@example.com", password_hash=hash_password("correct-horse-battery"))
        session.add(user)
        session.commit()
        session.add(
            PushSubscription(user_id=user.id, endpoint="https://fcm.example/x", p256dh="k", auth="a")
        )
        session.commit()

        service = PushService(session, user.id, pusher=build_pusher())
        with pytest.raises(PushNotConfigured):
            service.send(Notification(title="t", body="b"))


def test_a_mismatched_keypair_is_refused_at_startup(monkeypatch):
    """Half a keypair, or two halves from different pairs, must fail loudly.

    The failure this prevents is silent: browsers subscribe with the public key, the
    server signs with a private key that does not match, and every push comes back as an
    opaque 403 from the push service.
    """
    import app.services.push as push_module
    from app.scripts.vapid_keys import generate

    private_key, _ = generate()[1], None
    _, other_public = generate()[0], None
    adjusted = replace(settings, vapid_public_key=generate()[0], vapid_private_key=private_key)
    monkeypatch.setattr(push_module, "settings", adjusted)

    with pytest.raises(RuntimeError) as error:
        push_module.build_pusher()
    assert "does not match" in str(error.value)


def test_a_pem_private_key_is_accepted(monkeypatch):
    """A PEM pasted in by hand works too: only the DER form is required internally."""
    import base64

    import app.services.push as push_module
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.scripts.vapid_keys import generate

    _, der_token = generate()
    padded = (der_token + "=" * (-len(der_token) % 4)).replace("-", "+").replace("_", "/")
    loaded = serialization.load_der_private_key(base64.b64decode(padded), password=None)
    pem = loaded.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = base64.urlsafe_b64encode(
        loaded.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
    ).rstrip(b"=").decode()

    adjusted = replace(settings, vapid_public_key=public_key, vapid_private_key=pem)
    monkeypatch.setattr(push_module, "settings", adjusted)

    assert isinstance(push_module.build_pusher(), push_module.WebPusher)
    assert push_module._der_token(pem) == der_token
