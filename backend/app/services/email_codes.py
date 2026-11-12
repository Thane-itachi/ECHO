"""Six-digit email codes: issue, deliver, check, retire.

The rules live here rather than in the routes, so every caller (verification,
sign-in, password reset) gets the same behaviour:

* six digits from `secrets`, uniform
* five minute life, one use, five wrong guesses and the code is dead
* a new code retires every older live code for that address and purpose
* a sixty second cooldown per address and purpose, and hourly caps per address and
  per IP counted from this table (no counter that can drift)
* only a keyed digest is stored
* delivery failure raises, and the caller decides; it never silently "succeeds"

Nothing here reveals whether an address has an account. The routes answer the same
way either way.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import EmailCode, User
from app.services.mailer import EmailMessage, Mailer, MailError

logger = logging.getLogger("echo.email_codes")

VERIFY_EMAIL = "verify_email"
LOGIN_OTP = "login_otp"
PASSWORD_RESET = "password_reset"

_COOLDOWN = "wait a moment before asking for another code"
_TOO_MANY = "too many codes requested; try again later"
_BAD_CODE = "that code is not valid, or it has expired"


class CodeError(Exception):
    """Base for anything that stops a code being issued or accepted."""


class CodeCooldown(CodeError):
    """A code was issued too recently. Callers answer generically."""


class CodeRateLimited(CodeError):
    """Hourly cap reached for the address or the IP. Callers answer generically."""


class CodeRejected(CodeError):
    """Wrong, expired, already used, or out of attempts."""


class CodeDeliveryFailed(CodeError):
    """The provider refused or was unreachable. The code is burned."""


def _pepper() -> bytes:
    """The keying secret for stored digests.

    An explicit `ECHO_EMAIL_CODE_PEPPER` wins. Otherwise it is derived from the user
    signing secret, which must already be a real secret in production. `load_settings`
    refuses to start production with a placeholder there.
    """
    raw = settings.email_code_pepper or settings.user_jwt_secret
    return hashlib.sha256(f"echo:email-code:{raw}".encode()).digest()


def digest_code(email: str, purpose: str, code: str) -> str:
    message = f"{email.strip().lower()}|{purpose}|{code.strip()}".encode()
    return hmac.new(_pepper(), message, hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _live_codes(session: Session, email: str, purpose: str):
    return (
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .order_by(EmailCode.created_at.desc())
    )


def _count_since(session: Session, column, value, since) -> int:
    return int(
        session.scalar(select(func.count()).select_from(EmailCode).where(column == value, EmailCode.created_at >= since))
        or 0
    )


def _check_limits(session: Session, email: str, purpose: str, request_ip: str | None) -> None:
    now = utcnow()
    latest = session.scalars(_live_codes(session, email, purpose)).first()
    if latest is not None:
        # A live code exists: allow a resend only after the cooldown, measured from
        # the live code itself (expired codes do not block, they are already dead).
        age = (now - latest.created_at).total_seconds()
        if age < settings.email_code_cooldown_seconds:
            raise CodeCooldown(_COOLDOWN)
    hour_ago = now - timedelta(hours=1)
    if _count_since(session, EmailCode.email, email, hour_ago) >= settings.email_code_hourly_per_address:
        raise CodeRateLimited(_TOO_MANY)
    if request_ip and _count_since(session, EmailCode.request_ip, request_ip, hour_ago) >= settings.email_code_hourly_per_ip:
        raise CodeRateLimited(_TOO_MANY)


def _retire_live_codes(session: Session, email: str, purpose: str) -> None:
    session.execute(
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .values(consumed_at=utcnow())
    )


def _message_for(purpose: str, code: str, *, email: str) -> EmailMessage:
    ttl = settings.email_code_ttl_seconds
    minutes = max(1, round(ttl / 60))
    if purpose == VERIFY_EMAIL:
        subject = "Your ECHO verification code"
        lead = "Confirm your email address for ECHO."
    elif purpose == LOGIN_OTP:
        subject = "Your ECHO sign-in code"
        lead = "Here is the code to finish signing in to ECHO."
    elif purpose == PASSWORD_RESET:
        subject = "Your ECHO password reset code"
        lead = "Here is the code to choose a new ECHO password."
    else:  # pragma: no cover - guarded by the CHECK constraint
        raise ValueError(f"unknown purpose {purpose!r}")

    text = (
        f"{lead}\n\n"
        f"{code}\n\n"
        f"It expires in {minutes} minutes and can be used once.\n"
        "If you did not ask for this, you can ignore it: nothing has changed.\n"
    )
    html = (
        f"<p>{lead}</p>"
        f'<p style="font-size:28px;letter-spacing:6px;font-family:ui-monospace,monospace">{code}</p>'
        f"<p>It expires in {minutes} minutes and can be used once.<br>"
        "If you did not ask for this, you can ignore it: nothing has changed.</p>"
    )
    return EmailMessage(to=email, subject=subject, text=text, html=html)


def issue(
    session: Session,
    *,
    email: str,
    purpose: str,
    mailer: Mailer,
    user: User | None = None,
    request_ip: str | None = None,
) -> str:
    """Create a code, retire older ones, and hand it to the mailer.

    Returns the plaintext code (used only by the development echo in the route and by
    tests). Raises CodeCooldown / CodeRateLimited before touching the table, or
    CodeDeliveryFailed if the provider refuses.
    """
    email = email.strip().lower()
    _check_limits(session, email, purpose, request_ip)
    _retire_live_codes(session, email, purpose)

    code = _new_code()
    row = EmailCode(
        email=email,
        user_id=user.id if user is not None else None,
        purpose=purpose,
        code_hash=digest_code(email, purpose, code),
        expires_at=utcnow() + timedelta(seconds=settings.email_code_ttl_seconds),
        request_ip=request_ip,
    )
    session.add(row)
    session.flush()

    try:
        mailer.send(_message_for(purpose, code, email=email))
    except MailError as exc:
        # The code exists but nobody can receive it. Burn it so a later retry is not
        # blocked by a live code the user never saw, and report upwards.
        row.consumed_at = utcnow()
        session.flush()
        logger.error("email delivery failed for %s: %s", email, exc)
        raise CodeDeliveryFailed("the code could not be delivered") from exc
    return code


def consume(session: Session, *, email: str, purpose: str, code: str) -> EmailCode:
    """Check a code and retire it. Raises CodeRejected on anything but success."""
    email = email.strip().lower()
    submitted = code.strip()
    row = session.scalars(_live_codes(session, email, purpose)).first()
    if row is None:
        raise CodeRejected(_BAD_CODE)
    if row.attempts >= settings.email_code_max_attempts:
        raise CodeRejected(_BAD_CODE)
    if row.expires_at <= utcnow():
        # Expired but still open: close it so it stops costing attempts.
        row.consumed_at = utcnow()
        session.flush()
        raise CodeRejected(_BAD_CODE)
    if not hmac.compare_digest(row.code_hash, digest_code(email, purpose, submitted)):
        row.attempts += 1
        if row.attempts >= settings.email_code_max_attempts:
            row.consumed_at = utcnow()
        session.flush()
        raise CodeRejected(_BAD_CODE)
    row.consumed_at = utcnow()
    session.flush()
    return row
