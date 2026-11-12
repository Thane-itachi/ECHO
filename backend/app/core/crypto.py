"""Content encryption for memory bodies.

This decision is deliberately made *now*, before search, tags and AI extraction
exist, because it constrains all three:

* Memory/proposal body text is encrypted at rest with a per-user key derived from
  one master key (`HKDF(master, info=user_id)`).
* The derived plaintext used for full-text search lives in its own column
  (`search_text`). Search therefore reads a *derived index*, never the ciphertext,
  and never the ciphertext of another user.
* If ECHO later moves to true end-to-end encryption (client holds the key), the
  only change is `MemoryRepository._index_text` plus shipping search client-side.
  The schema does not change.

A dev-only `NullCipher` keeps local setups frictionless; it refuses to run when
ECHO_ENV=production.
"""
from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings, settings


class CipherError(RuntimeError):
    pass


class ContentCipher:
    scheme = "f1"

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) < 16:
            raise CipherError("master key must be at least 16 bytes")
        self._master = master_key

    def _fernet(self, user_id: str) -> Fernet:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"echo/user-content/v1", info=user_id.encode())
        return Fernet(base64.urlsafe_b64encode(hkdf.derive(self._master)))

    def encrypt(self, plaintext: str, user_id: str) -> str:
        token = self._fernet(user_id).encrypt(plaintext.encode()).decode()
        return f"{self.scheme}:{token}"

    def decrypt(self, value: str, user_id: str) -> str:
        if not value.startswith(f"{self.scheme}:"):
            raise CipherError("ciphertext scheme mismatch")
        try:
            return self._fernet(user_id).decrypt(value[len(self.scheme) + 1 :].encode()).decode()
        except InvalidToken as exc:
            raise CipherError("ciphertext could not be decrypted for this owner") from exc


class NullCipher:
    """Plaintext passthrough. Development only."""

    scheme = "p1"

    def __init__(self, *, allow: bool = True) -> None:
        self._allow = allow

    def encrypt(self, plaintext: str, user_id: str) -> str:
        if not self._allow:
            raise CipherError("no data key configured; refusing to store plaintext content")
        return f"{self.scheme}:{plaintext}"

    def decrypt(self, value: str, user_id: str) -> str:
        if not value.startswith(f"{self.scheme}:"):
            raise CipherError("ciphertext scheme mismatch")
        return value[len(self.scheme) + 1 :]


def build_cipher(config: Settings | None = None) -> ContentCipher | NullCipher:
    """Build the content cipher for a config (the ambient settings by default).

    Taking the config as an argument keeps this testable without touching process
    globals: the behaviour under test is "key present -> encrypt", not "whatever
    this machine's environment happens to say".
    """
    cfg = config or settings
    if cfg.data_key:
        return ContentCipher(base64.urlsafe_b64decode(cfg.data_key))
    return NullCipher(allow=not cfg.is_production)


@lru_cache(maxsize=1)
def get_default_cipher() -> ContentCipher | NullCipher:
    return build_cipher()


def new_data_key() -> str:
    """Convenience for `python -m app.scripts.gen_key`."""
    import os

    return base64.urlsafe_b64encode(os.urandom(32)).decode()
