"""The reminder email: one template, and a way out of it.

Two decisions worth naming.

The opt-out link has to work from a mail client, which means it must prove it is
about *this account* without a session. So it carries `user_id` plus an HMAC keyed
with the deployment secret: changing the id in the URL produces a link that verifies
for nobody. There is no expiry, deliberately, because an unsubscribe link in an old
email still has to work; a link that stops working is how you get reported as spam.

The first click does not unsubscribe. Mail clients and security scanners fetch every
link in a message before a person sees it, so a GET that opts people out silently
would unsubscribe users who never clicked. GET renders a page with a button; only the
POST turns anything off.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from app.core.config import settings
from app.db.models import User
from app.services.mailer import EmailMessage

OPT_OUT_PATH = "/api/reminders/email/opt-out"


class BadToken(ValueError):
    """The link is not for any account on this server."""


def _secret() -> bytes:
    return hashlib.sha256(f"echo:reminder-email-optout:{settings.user_jwt_secret}".encode()).digest()


def _signature(user_id: str) -> str:
    return hmac.new(_secret(), f"echo:reminder-email:{user_id}".encode(), hashlib.sha256).hexdigest()


def token_for(user_id: str) -> str:
    return f"{user_id}.{_signature(user_id)}"


def user_id_from_token(token: str) -> str:
    """Return the account this link is about, or raise `BadToken`."""
    if not token or "." not in token:
        raise BadToken("malformed token")
    user_id, _, signature = token.rpartition(".")
    if not user_id or not signature:
        raise BadToken("malformed token")
    if not hmac.compare_digest(signature, _signature(user_id)):
        raise BadToken("signature does not match")
    return user_id


def opt_out_url(user_id: str) -> str:
    return f"{settings.public_api_url}{OPT_OUT_PATH}?token={token_for(user_id)}"


def _fold(title: str, limit: int = 120) -> str:
    flat = " ".join(title.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _when(due_at) -> str:
    """Naive UTC in, unambiguous UTC out. A reminder email that guesses the wrong
    timezone is worse than one that states the one it knows."""
    if due_at is None:
        return "now"
    return f"{due_at:%a %d %b %Y, %H:%M} UTC"


def build_message(user: User, payload: dict) -> EmailMessage:
    """The reminder itself. Plain text first: it is the version that always renders."""
    title = _fold(str(payload.get("title") or "A promise you asked ECHO to keep"))
    due = payload.get("due_at")
    when = _when(_parse(due))
    reminders_url = f"{settings.public_app_url}/reminders"
    opt_out = opt_out_url(user.id)
    subject = f"Reminder: {title}"

    text = (
        f"{title}\n\n"
        f"Due {when}.\n\n"
        f"Open your reminders: {reminders_url}\n\n"
        "--\n"
        "You get this because reminder email is on for your ECHO account.\n"
        f"Turn it off for good: {opt_out}\n"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;background:#f6f1e8;padding:28px 16px;font-family:Georgia,'Times New Roman',serif;color:#2f2a24">
  <div style="max-width:520px;margin:0 auto;background:#fffdf8;border:1px solid #e2d8c7;border-radius:6px;padding:28px">
    <p style="margin:0 0 18px;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#8a7c6a">ECHO reminder</p>
    <h1 style="margin:0 0 10px;font-size:22px;line-height:1.3;font-weight:normal">{_escape(title)}</h1>
    <p style="margin:0 0 22px;font-size:15px;color:#5c5347">Due {_escape(when)}.</p>
    <p style="margin:0 0 24px">
      <a href="{_escape(reminders_url)}" style="display:inline-block;background:#2f2a24;color:#fffdf8;text-decoration:none;padding:10px 18px;border-radius:4px;font-size:14px">Open your reminders</a>
    </p>
    <p style="margin:0;font-size:12px;line-height:1.6;color:#8a7c6a;border-top:1px solid #ece1cf;padding-top:14px">
      You get this because reminder email is on for your ECHO account.<br>
      <a href="{_escape(opt_out)}" style="color:#8a7c6a">Turn off reminder emails</a>
    </p>
  </div>
</body></html>"""
    return EmailMessage(
        to=user.email,
        subject=subject,
        text=text,
        html=html,
        # Not a bulk sender: it is a transactional message about something the account
        # holder asked for. A List-Unsubscribe header still helps clients show "unsubscribe"
        # without hunting for the footer link.
        headers={
            "List-Unsubscribe": f"<{opt_out}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


def _parse(value) -> object:
    from datetime import datetime

    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def page(*, heading: str, text: str, button: str | None = None, action: str | None = None, token: str | None = None) -> str:
    """The opt-out page, styled like the app rather than like a bare API response."""
    form = ""
    if button and action and token:
        form = f"""
      <form method="post" action="{OPT_OUT_PATH}" style="margin:24px 0 0">
        <input type="hidden" name="token" value="{_escape(token)}">
        <input type="hidden" name="action" value="{_escape(action)}">
        <button type="submit" style="background:#2f2a24;color:#fffdf8;border:0;padding:11px 20px;border-radius:4px;font-size:15px;font-family:inherit;cursor:pointer">{_escape(button)}</button>
      </form>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECHO \u2014 reminder email</title></head>
<body style="margin:0;background:#f6f1e8;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;font-family:Georgia,'Times New Roman',serif;color:#2f2a24">
  <div style="max-width:480px;width:100%;background:#fffdf8;border:1px solid #e2d8c7;border-radius:6px;padding:32px">
    <p style="margin:0 0 16px;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#8a7c6a">ECHO</p>
    <h1 style="margin:0 0 12px;font-size:21px;line-height:1.35;font-weight:normal">{_escape(heading)}</h1>
    <p style="margin:0;font-size:15px;line-height:1.6;color:#5c5347">{text}</p>{form}
  </div>
</body></html>"""
