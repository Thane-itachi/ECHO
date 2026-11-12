"""Minimal RFC 6238 TOTP (no dependency, ~20 lines of hmac)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

DIGITS = 6
STEP = 30


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int, digits: int = DIGITS) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def totp_now(secret: str, *, at: float | None = None, step: int = STEP, digits: int = DIGITS) -> str:
    moment = time.time() if at is None else at
    return _code(secret, int(moment // step), digits)


def verify_totp(secret: str | None, code: str | None, *, at: float | None = None, window: int = 1,
                step: int = STEP, digits: int = DIGITS) -> bool:
    if not secret or not code:
        return False
    code = code.strip()
    if not code.isdigit() or len(code) != digits:
        return False
    moment = time.time() if at is None else at
    base = int(moment // step)
    return any(hmac.compare_digest(_code(secret, base + drift, digits), code) for drift in range(-window, window + 1))


def otpauth_url(secret: str, account: str, issuer: str = "ECHO Admin") -> str:
    return f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits={DIGITS}&period={STEP}"
