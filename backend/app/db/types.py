"""Column types that make "stored in the clear" impossible to write by accident.

`SealedSecret` is a `TypeDecorator`, not a helper that callers must remember to use.
Any code path that writes the column gets the sealing for free, and any code path that
reads it gets the plaintext back without knowing a key exists. That is the difference
between "administrators' TOTP seeds are encrypted" and "administrators' TOTP seeds are
encrypted on the paths somebody remembered".

Sealed values use their own key derivation (`HKDF` context `echo/system-secret/v1`),
not a user's content key, so the two are cryptographically unrelated.

The key comes from the process cipher, not from a request: any worker must be able to
verify an administrator's login, so this cannot depend on which service object happens
to handle the call.
"""
from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.crypto import process_cipher


class SealedSecret(TypeDecorator[str]):
    """Encrypts a short platform secret on write, decrypts it on read."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001 - SQLAlchemy hook
        if value is None:
            return None
        return process_cipher().seal(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001 - SQLAlchemy hook
        if value is None:
            return None
        return process_cipher().unseal(value)
