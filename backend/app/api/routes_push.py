"""Notifications to the user's own devices (Web Push).

Four calls: ask whether notifications are configured and get the public key, register
this browser, forget this browser, and send one test notification so "did it work?" is
answerable without waiting for a reminder to come due.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.config import settings
from app.core.errors import EchoError, InvalidRequest, NotFound
from app.db.models import User
from app.services.push import (
    InvalidSubscription,
    Notification,
    PushNotConfigured,
    PushService,
)

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=64)


class SubscriptionRequest(BaseModel):
    endpoint: str = Field(max_length=512)
    keys: SubscriptionKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=512)


def get_pusher(request: Request):
    """The configured transport, swappable per app instance so tests never dial out."""
    return getattr(request.app.state, "pusher", None)


@router.get("/key")
def public_key() -> dict:
    """Enough to decide whether to show the toggle, and the key to subscribe with."""
    return {
        "enabled": settings.push_enabled,
        "public_key": settings.vapid_public_key if settings.push_enabled else None,
    }


@router.get("/subscriptions")
def list_subscriptions(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    pusher=Depends(get_pusher),
) -> dict:
    """How many devices this account has, never which ones: no endpoint leaves here."""
    service = PushService(db, user.id, pusher=pusher)
    devices = service.devices()
    return {
        "enabled": settings.push_enabled,
        "count": len(devices),
        "devices": [
            {
                "id": device.id,
                "label": _label(device.user_agent),
                "created_at": device.created_at,
                "last_success_at": device.last_success_at,
            }
            for device in devices
        ],
    }


@router.post("/subscribe", status_code=201)
def subscribe(
    payload: SubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    pusher=Depends(get_pusher),
) -> dict:
    service = PushService(db, user.id, pusher=pusher)
    try:
        device = service.subscribe(
            {"endpoint": payload.endpoint, "keys": payload.keys.model_dump()},
            user_agent=request.headers.get("user-agent"),
        )
    except PushNotConfigured as exc:
        # 503, not 400: the browser did nothing wrong, this deployment cannot sign.
        raise EchoError(
            "notifications are not configured on this server",
            code="push_not_configured",
            status_code=503,
        ) from exc
    except InvalidSubscription as exc:
        raise InvalidRequest(str(exc)) from exc
    db.commit()
    return {"id": device.id, "label": _label(device.user_agent), "count": service.device_count()}


@router.post("/unsubscribe")
def unsubscribe(
    payload: UnsubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    pusher=Depends(get_pusher),
) -> dict:
    service = PushService(db, user.id, pusher=pusher)
    removed = service.unsubscribe(payload.endpoint)
    db.commit()
    # Forgetting an endpoint twice is not an error: the phone may be gone already.
    return {"removed": removed, "count": service.device_count()}


@router.post("/test")
def send_test(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    pusher=Depends(get_pusher),
) -> dict:
    """One notification to every device on this account, so the setup can be proved."""
    service = PushService(db, user.id, pusher=pusher)
    if service.device_count() == 0:
        raise NotFound("no device is subscribed to notifications yet")
    try:
        result = service.send(
            Notification(
                title="ECHO is listening",
                body="That is what a reminder will look like on this device.",
                url="/reminders",
                tag="echo-test",
                kind="test",
            )
        )
    except PushNotConfigured as exc:
        raise EchoError(
            "notifications are not configured on this server",
            code="push_not_configured",
            status_code=503,
        ) from exc
    db.commit()
    return {"attempted": result.attempted, **result.as_dict()}


def _label(user_agent: str | None) -> str:
    """A short, human name for a device, from the user agent it subscribed with."""
    agent = (user_agent or "").lower()
    if "iphone" in agent:
        return "iPhone"
    if "ipad" in agent:
        return "iPad"
    if "android" in agent:
        return "Android phone"
    if "macintosh" in agent or "mac os" in agent:
        return "Mac"
    if "windows" in agent:
        return "Windows PC"
    if "linux" in agent:
        return "Linux machine"
    return "Browser"
