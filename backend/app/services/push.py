"""Web Push: notifications that reach a phone with the app closed.

How the pieces fit, because this is the part people get wrong:

* The browser hands us a *subscription* (an endpoint URL plus two keys). We store it
  against the user. The endpoint is a capability: anyone holding it can push to that
  device, so it is never logged and never sent back to a client.
* Each notification is encrypted to that device's keys before it reaches the push
  service. Google's or Mozilla's server relays ciphertext it cannot read, which is why
  the reminder text is encrypted end to end and not just over TLS.
* A subscription that the push service has retired answers 404 or 410. That is not an
  error to retry: the device is gone (cleared data, uninstalled, expired) and the row
  is deleted. Anything else increments a counter so a permanently broken device stops
  being hammered.

With no VAPID keypair configured the service refuses to subscribe anyone, so a
deployment cannot silently collect endpoints it has no way to notify.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import PushSubscription

logger = logging.getLogger("echo.push")

#: Field limits from the Push API. Longer endpoints are refused rather than truncated,
#: because a truncated endpoint is a silent dead end.
MAX_ENDPOINT = 512
MAX_KEY = 200
MAX_AUTH = 64
#: A device that fails this many times in a row without ever succeeding is dropped.
MAX_FAILURES = 5


class PushNotConfigured(RuntimeError):
    """No VAPID keypair: notifications cannot be signed, so nobody may subscribe."""


class InvalidSubscription(ValueError):
    """The browser sent something that is not a usable subscription."""


@dataclass(frozen=True)
class Notification:
    """What the user sees. Kept small and boring: a title, a line, and where to go."""

    title: str
    body: str
    url: str = "/vault"
    tag: str = "echo"
    kind: str = "generic"

    def as_payload(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "tag": self.tag,
            "kind": self.kind,
        }


@dataclass
class DeliveryResult:
    sent: int = 0
    pruned: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return self.sent + self.failed + self.pruned

    def as_dict(self) -> dict:
        return {"sent": self.sent, "pruned": self.pruned, "failed": self.failed}


class NullPusher:
    """Local development, or a deployment with no keypair.

    Refuses sends so nothing pretends to have reached a phone, but keeps the same
    interface so the rest of the code never branches on configuration.
    """

    name = "none"
    configured = False

    def send(self, subscription: PushSubscription, payload: dict) -> None:
        raise PushNotConfigured("no VAPID keypair configured")


def _b64url(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _der_token(key: str) -> str:
    """Normalise a private key to the form pywebpush actually wants.

    pywebpush base64url-decodes the string and parses the result as DER, so the value in
    `.env` is the base64url body, not a PEM (a PEM header also contains spaces, which a
    shell-read env file truncates). A PEM pasted in by hand is converted here instead of
    failing at the first send.
    """
    key = key.strip()
    if not key.startswith("-----BEGIN"):
        return key
    from cryptography.hazmat.primitives import serialization

    loaded = serialization.load_pem_private_key(key.encode(), password=None)
    der = loaded.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _b64url(der)


def public_key_of(private_key: str) -> str:
    """The base64url public key that belongs to this private key.

    Used at startup to catch a mismatched pair: a public key from a different keypair
    yields subscriptions the server cannot sign for, and every push is refused by the
    push service with an opaque 403.
    """
    import base64

    from cryptography.hazmat.primitives import serialization

    token = _der_token(private_key)
    padded = (token + "=" * (-len(token) % 4)).replace("-", "+").replace("_", "/")
    der = base64.b64decode(padded)
    loaded = serialization.load_der_private_key(der, password=None)
    raw = loaded.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(raw)


class WebPusher:
    """pywebpush, which does the AES-GCM encryption and the VAPID signature."""

    name = "webpush"
    configured = True

    def __init__(self, *, private_key: str, subject: str, timeout: float) -> None:
        self.private_key = private_key
        self.subject = subject
        self.timeout = timeout

    def send(self, subscription: PushSubscription, payload: dict) -> None:
        from pywebpush import webpush

        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=_der_token(self.private_key),
            vapid_claims={"sub": self.subject},
            timeout=self.timeout,
        )


class CapturingPusher:
    """Test double: records what would have been delivered, and can fail on demand."""

    name = "capture"
    configured = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.fail_status: int | None = None

    def send(self, subscription: PushSubscription, payload: dict) -> None:
        if self.fail_status is not None:
            raise _FakePushError(self.fail_status)
        self.sent.append((subscription.endpoint, payload))

    def payloads(self) -> list[dict]:
        return [payload for _, payload in self.sent]


class _FakePushError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"push service said {status_code}")
        self.response = _FakeResponse(status_code)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


def build_pusher():
    if not settings.push_enabled:
        return NullPusher()
    private_key = settings.vapid_private_key or ""
    public_key = settings.vapid_public_key or ""
    try:
        derived = public_key_of(private_key)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same problem
        raise RuntimeError(
            "ECHO_VAPID_PRIVATE_KEY is not a usable EC P-256 private key; "
            "regenerate the pair with `python -m app.scripts.vapid_keys`"
        ) from exc
    if derived != public_key:
        raise RuntimeError(
            "ECHO_VAPID_PUBLIC_KEY does not match ECHO_VAPID_PRIVATE_KEY; browsers would "
            "subscribe with a key this server cannot sign for. Regenerate both together."
        )
    return WebPusher(
        private_key=private_key,
        subject=settings.vapid_subject,
        timeout=settings.push_timeout_seconds,
    )


def describe(pusher) -> str:
    if isinstance(pusher, WebPusher):
        return "web push (VAPID configured)"
    return "none — notifications are not delivered (no VAPID keypair)"


def normalise_subscription(payload: dict) -> tuple[str, str, str]:
    """Pull (endpoint, p256dh, auth) out of a browser subscription, or refuse it."""
    endpoint = str(payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = str((keys or {}).get("p256dh") or "").strip()
    auth = str((keys or {}).get("auth") or "").strip()
    if not endpoint.startswith("https://"):
        raise InvalidSubscription("a subscription endpoint must be an https URL")
    if len(endpoint) > MAX_ENDPOINT:
        raise InvalidSubscription("that subscription endpoint is too long")
    if not p256dh or len(p256dh) > MAX_KEY:
        raise InvalidSubscription("the subscription is missing its browser key")
    if not auth or len(auth) > MAX_AUTH:
        raise InvalidSubscription("the subscription is missing its auth secret")
    return endpoint, p256dh, auth


class PushService:
    """Everything that touches the push_subscriptions table, scoped to one user."""

    def __init__(self, session: Session, user_id: str, *, pusher=None) -> None:
        self.session = session
        self.user_id = user_id
        self.pusher = pusher if pusher is not None else build_pusher()

    def devices(self) -> list[PushSubscription]:
        return list(
            self.session.scalars(
                select(PushSubscription)
                .where(PushSubscription.user_id == self.user_id)
                .order_by(PushSubscription.created_at)
            )
        )

    def device_count(self) -> int:
        return len(self.devices())

    def subscribe(self, payload: dict, *, user_agent: str | None = None) -> PushSubscription:
        """Register this browser. Re-subscribing the same endpoint is a no-op update.

        The endpoint is unique across the table: the same phone signing in as another
        user must not leave the first account able to notify it.
        """
        if not getattr(self.pusher, "configured", False):
            raise PushNotConfigured("notifications are not configured on this server")
        endpoint, p256dh, auth = normalise_subscription(payload)
        existing = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        if existing is not None:
            existing.user_id = self.user_id
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = (user_agent or existing.user_agent or "")[:200] or None
            existing.failure_count = 0
            self.session.flush()
            return existing
        subscription = PushSubscription(
            user_id=self.user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=(user_agent or "")[:200] or None,
        )
        try:
            with self.session.begin_nested():
                self.session.add(subscription)
        except IntegrityError:
            # Another request registered the same endpoint between our read and write.
            subscription = self.session.scalar(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
            if subscription is None:  # pragma: no cover - would mean the row vanished
                raise
            subscription.user_id = self.user_id
        self.session.flush()
        return subscription

    def unsubscribe(self, endpoint: str) -> bool:
        subscription = self.session.scalar(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == self.user_id,
            )
        )
        if subscription is None:
            return False
        self.session.delete(subscription)
        self.session.flush()
        return True

    def send(self, notification: Notification) -> DeliveryResult:
        """Deliver to every device this user registered. Never raises for one bad row."""
        if not getattr(self.pusher, "configured", False):
            raise PushNotConfigured("notifications are not configured on this server")
        result = DeliveryResult()
        for subscription in self.devices():
            try:
                self.pusher.send(subscription, notification.as_payload())
            except Exception as exc:  # noqa: BLE001 - one device must not break the rest
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    # The device is gone: retire the row, do not retry it.
                    logger.info("push endpoint retired by the service (%s); removing", status)
                    self.session.delete(subscription)
                    result.pruned += 1
                    continue
                subscription.failure_count += 1
                result.failed += 1
                result.errors.append(f"status={status or 'error'}")
                logger.warning("push failed for a device (status=%s): %s", status, type(exc).__name__)
                if subscription.failure_count >= MAX_FAILURES:
                    # Broken for every attempt so far: stop paying for it.
                    self.session.delete(subscription)
                    result.pruned += 1
                continue
            subscription.failure_count = 0
            subscription.last_success_at = utcnow()
            result.sent += 1
        self.session.flush()
        return result
