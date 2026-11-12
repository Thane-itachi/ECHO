"""Administrator enrolment links.

The point of this module: an administrator never receives a password from anyone.
Whoever creates the account (a founder in the console, or an operator on the server)
only ever issues a single-use link. The person opening it chooses their own password
and enrols their own authenticator app in the same sitting, so:

* nobody but the account holder ever knows the password,
* nobody but the account holder ever knows the TOTP secret,
* a link that leaks is useless without being opened before it expires, and useless
  twice.

The token is 32 random bytes, stored only as a SHA-256 digest. It is never written to
the audit trail, never logged, and never returned by any endpoint except the one that
minted it (the CLI, or the founder-only console endpoint).

Deliberately *not* here: password recovery by email. A recovery flow that emails a
reset link is only as strong as the mailbox, and this console's whole posture is that
an admin account is a key held by one person. If someone is locked out, a founder
issues a fresh enrolment link; if the only founder is locked out, that is a
server-level operation (`create_admin --email … --invite`).
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import secrets
from datetime import timedelta

import qrcode
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.admin.permissions import FOUNDER, is_known_role
from app.core.errors import Conflict, InvalidRequest, NotFound, Unauthorized
from app.core.mfa import generate_secret, otpauth_url, verify_totp
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.models import AdminInvite, AdminUser
from app.repositories.system import AuditRepository

INVITE_TTL_HOURS = 72
_TOKEN_BYTES = 32
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def qr_data_uri(payload: str) -> str:
    """A PNG data URI of the otpauth URL, so a phone can scan what it cannot type."""
    code = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(payload)
    code.make(fit=True)
    buffer = io.BytesIO()
    code.make_image(fill_color="#17130e", back_color="#fbf7f0").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def issue_invite(
    session: Session,
    *,
    email: str,
    role: str = FOUNDER,
    issued_by: str | None = None,
    ttl_hours: int = INVITE_TTL_HOURS,
) -> tuple[AdminInvite, str]:
    """Mint a single-use enrolment link. Returns the row and the raw token, once."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise InvalidRequest("must be a valid email address")
    if not is_known_role(role):
        raise InvalidRequest("unknown administrator role")

    # One live link per address: re-issuing silently retires the previous one, so an
    # old link cannot be used to take the account over after a newer one was sent.
    session.execute(
        delete(AdminInvite).where(AdminInvite.email == email, AdminInvite.used_at.is_(None))
    )

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    invite = AdminInvite(
        email=email,
        role=role,
        token_hash=_digest(token),
        expires_at=utcnow() + timedelta(hours=ttl_hours),
        issued_by=issued_by,
    )
    session.add(invite)
    AuditRepository(session).record(
        action="admin.invite_issued",
        actor_id=issued_by,
        actor_type="admin" if issued_by else "system",
        target_type="admin_invite",
        target_id=invite.id,
        detail={"email": email, "role": role, "expires_hours": ttl_hours},
    )
    session.commit()
    return invite, token


def resolve_invite(session: Session, token: str) -> AdminInvite:
    """Look a token up and enforce single use and expiry."""
    cleaned = (token or "").strip()
    if not cleaned:
        raise NotFound("this enrolment link is not valid")
    invite = session.scalars(
        select(AdminInvite).where(AdminInvite.token_hash == _digest(cleaned))
    ).one_or_none()
    if invite is None:
        raise NotFound("this enrolment link is not valid")
    if invite.used_at is not None:
        raise Conflict("this enrolment link has already been used")
    if invite.expires_at <= utcnow():
        raise Conflict("this enrolment link has expired")
    return invite


def enrol(
    session: Session, *, token: str, password: str
) -> tuple[AdminUser, str, str, AdminInvite]:
    """Set the account's own password and enrol a fresh TOTP secret.

    Returns the account, the secret, the otpauth URL and the invite. The account is
    created (or reset) here; it only becomes usable once the holder proves they can
    generate a code from the secret they were just shown.
    """
    invite = resolve_invite(session, token)
    try:
        password_hash = hash_password(password)
    except ValueError as exc:  # length policy
        raise InvalidRequest(str(exc)) from exc

    secret = generate_secret()
    account = session.scalars(
        select(AdminUser).where(AdminUser.email == invite.email)
    ).one_or_none()
    created = account is None
    if account is None:
        account = AdminUser(
            email=invite.email,
            password_hash=password_hash,
            mfa_secret=secret,
            role=invite.role,
            is_active=True,
        )
        session.add(account)
    else:
        account.password_hash = password_hash
        account.mfa_secret = secret
        account.role = invite.role
        account.is_active = True

    session.flush()
    AuditRepository(session).record(
        action="admin.enrolment_started",
        actor_id=account.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
        detail={"email": invite.email, "created": created, "role": account.role},
    )
    session.commit()
    return account, secret, otpauth_url(secret, account.email), invite


def confirm_enrolment(session: Session, *, token: str, code: str) -> AdminUser:
    """Prove the secret was captured, then burn the link."""
    invite = resolve_invite(session, token)
    account = session.scalars(
        select(AdminUser).where(AdminUser.email == invite.email)
    ).one_or_none()
    if account is None:
        raise InvalidRequest("this enrolment link has not been started yet")
    if not verify_totp(account.mfa_secret, code):
        raise Unauthorized("that code did not match the secret shown")

    invite.used_at = utcnow()
    AuditRepository(session).record(
        action="admin.enrolled",
        actor_id=account.id,
        actor_type="admin",
        target_type="admin",
        target_id=account.id,
        detail={"email": invite.email, "role": account.role},
    )
    session.commit()
    return account


def revoke_invites(session: Session, *, email: str) -> int:
    """Cancel every open link for an address. Returns how many were live."""
    result = session.execute(
        delete(AdminInvite).where(
            AdminInvite.email == (email or "").strip().lower(),
            AdminInvite.used_at.is_(None),
        )
    )
    session.commit()
    return int(result.rowcount or 0)
