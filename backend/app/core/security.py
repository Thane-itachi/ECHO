"""Password hashing and audience-separated tokens.

The audience split is structural, not cosmetic: user tokens and admin tokens are
signed with *different* secrets and carry different `aud` claims. A user token
cannot be replayed against an admin route even if someone leaks one secret, and
admin tokens additionally require an MFA claim that only /admin/auth/token sets.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

import jwt

from app.core.config import settings
from app.core.time import utcnow

USER_AUDIENCE = "echo:user"
ADMIN_AUDIENCE = "echo:admin"
_ALGORITHM = "HS256"
_HASH_SCHEME = "pbkdf2_sha256"
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


class TokenError(Exception):
    """Any invalid, expired, wrong-audience or MFA-less token."""


def hash_password(password: str, *, iterations: int | None = None) -> str:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")
    rounds = iterations or settings.password_iterations
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"{_HASH_SCHEME}${rounds}${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, raw_rounds, raw_salt, raw_hash = stored.split("$")
        if scheme != _HASH_SCHEME:
            return False
        rounds = int(raw_rounds)
        salt = base64.b64decode(raw_salt)
        expected = base64.b64decode(raw_hash)
    except (ValueError, TypeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return hmac.compare_digest(derived, expected)


# Pre-computed so a login for an unknown email costs the same as a wrong password.
DUMMY_HASH = hash_password("echo-timing-equalizer")


def _secret_for(audience: str) -> str:
    if audience == ADMIN_AUDIENCE:
        return settings.admin_jwt_secret
    if audience == USER_AUDIENCE:
        return settings.user_jwt_secret
    raise TokenError(f"unknown audience {audience!r}")


def create_access_token(
    subject: str,
    *,
    audience: str = USER_AUDIENCE,
    ttl_seconds: int | None = None,
    mfa: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    issued = utcnow()
    ttl = ttl_seconds
    if ttl is None:
        ttl = settings.admin_token_ttl_seconds if audience == ADMIN_AUDIENCE else settings.user_token_ttl_seconds
    payload: dict[str, Any] = {
        "sub": subject,
        "aud": audience,
        "typ": "access",
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl)).timestamp()),
    }
    if audience == ADMIN_AUDIENCE:
        payload["mfa"] = bool(mfa)
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _secret_for(audience), algorithm=_ALGORITHM)


def decode_access_token(token: str, *, audience: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _secret_for(audience),
            algorithms=[_ALGORITHM],
            audience=audience,
            options={"require": ["exp", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise TokenError("token has no subject")
    if audience == ADMIN_AUDIENCE and payload.get("mfa") is not True:
        raise TokenError("admin token is missing the MFA claim")
    return payload
