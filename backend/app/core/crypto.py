"""Content encryption and the blind search index.

Two separate concerns live here, and both were decided before search and AI
extraction were built, because they constrain everything downstream.

1. **Content encryption.** Memory bodies *and* titles are encrypted at rest with a
   per-user key derived from one master key (`HKDF(master, info=user_id)`). Person
   notes and proposal bodies use the same scheme. Nothing user-written is stored as
   readable text.

2. **Search without plaintext.** Searching used to read a lowercased plaintext
   column, which leaked the whole corpus. It now reads a *blind index*: for every
   word we store only keyed HMAC tokens (`bits = HMAC-SHA256(per-user search key,
   token)`), plus a 3- and 4-character prefix token so type-ahead still works.
   Tokens are base32 (a-z, 2-7) so they can never contain SQL `LIKE` metacharacters,
   and the key is derived per user, so the same word in two vaults hashes
   differently and a stolen database cannot be attacked with a wordlist across
   users.

   Trade-off, stated plainly: a blind index supports term and prefix matching, not
   relevance ranking and not substring search inside a word. Postgres can rank
   matches afterwards (recency, category); if ECHO later needs semantic search it
   moves to embeddings of *decrypted-on-the-server* content, which is a conscious
   privacy decision, not an accident.

A dev-only `NullCipher` keeps local setups frictionless; it refuses to run when
ECHO_ENV=production.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
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

    # ---------------------------------------------------------------- documents
    def encrypt_bytes(self, data: bytes, user_id: str) -> bytes:
        return self._fernet(user_id).encrypt(data)

    def decrypt_bytes(self, blob: bytes, user_id: str) -> bytes:
        try:
            return self._fernet(user_id).decrypt(blob)
        except InvalidToken as exc:
            raise CipherError("document could not be decrypted for this owner") from exc


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

    def encrypt_bytes(self, data: bytes, user_id: str) -> bytes:
        if not self._allow:
            raise CipherError("no data key configured; refusing to store plaintext documents")
        return b"p1:" + data

    def decrypt_bytes(self, blob: bytes, user_id: str) -> bytes:
        if not blob.startswith(b"p1:"):
            raise CipherError("ciphertext scheme mismatch")
        return blob[3:]


AnyCipher = ContentCipher | NullCipher

_WORD_RE = re.compile(r"[^0-9a-z]+")
_INDEXED_PREFIXES = (3, 4)
MAX_INDEX_TOKENS = 4000


class BlindIndex:
    """Keyed token index: searchable, not readable.

    `index(user_id, text)` returns a space-delimited string of base32 tokens. Query
    it with `query_clauses()`, which yields SQLAlchemy predicates for one owner.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) < 16:
            raise CipherError("master key must be at least 16 bytes")
        self._master = master_key

    @classmethod
    def from_cipher(cls, cipher: AnyCipher) -> "BlindIndex | None":
        """Derive the index from the cipher that protects the same data.

        Keeping them tied together is what stops the old failure mode from coming
        back: a deployment with an encryption key can never silently keep a plaintext
        index, because the index is built from the cipher, not from a second setting.
        """
        master = getattr(cipher, "_master", None)
        return cls(master) if isinstance(master, (bytes, bytearray)) and len(master) >= 16 else None

    # ------------------------------------------------------------------- tokens
    def _key(self, user_id: str) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"echo/blind-index/v1",
            info=f"search\u0000{user_id}".encode(),
        )
        return hkdf.derive(self._master)

    @staticmethod
    def _token(key: bytes, term: str) -> str:
        digest = hmac.new(key, term.encode(), hashlib.sha256).digest()
        # base32 -> only [a-z2-7] once lowercased, so LIKE has nothing to escape.
        return base64.b32encode(digest[:10]).decode().lower().rstrip("=")

    @staticmethod
    def words(text: str) -> list[str]:
        return [word for word in _WORD_RE.split(text.lower()) if len(word) >= 2]

    @staticmethod
    def _stored_variants(word: str) -> list[str]:
        variants = {word}
        for size in _INDEXED_PREFIXES:
            if len(word) > size:
                variants.add(word[:size])
        return sorted(variants)

    def index(self, user_id: str, *texts: str) -> str:
        key = self._key(user_id)
        tokens: set[str] = set()
        for text in texts:
            for word in self.words(text or ""):
                for variant in self._stored_variants(word):
                    tokens.add(self._token(key, variant))
                    if len(tokens) >= MAX_INDEX_TOKENS:
                        return " " + " ".join(sorted(tokens)) + " "
        return " " + " ".join(sorted(tokens)) + " "

    def query_terms(self, user_id: str, query: str, *, max_words: int = 8) -> list[str]:
        """Hashed tokens to look for: one SQL predicate group per query word."""
        key = self._key(user_id)
        groups: list[str] = []
        for word in self.words(query)[:max_words]:
            probe = word if len(word) <= _INDEXED_PREFIXES[-1] else word[:_INDEXED_PREFIXES[-1]]
            groups.append(self._token(key, probe))
        return groups


def build_cipher(config: Settings | None = None) -> AnyCipher:
    """Build the content cipher for a config (the ambient settings by default).

    Taking the config as an argument keeps this testable without touching process
    globals: the behaviour under test is "key present -> encrypt", not "whatever
    this machine's environment happens to say".
    """
    cfg = config or settings
    if cfg.data_key:
        return ContentCipher(base64.urlsafe_b64decode(cfg.data_key))
    return NullCipher(allow=not cfg.is_production)


def build_blind_index(config: Settings | None = None) -> BlindIndex | None:
    """The blind index needs a real key. Without one (dev, plaintext mode) search
    falls back to plaintext matching, and `MemoryRepository` says so out loud."""
    cfg = config or settings
    if not cfg.data_key:
        return None
    return BlindIndex(base64.urlsafe_b64decode(cfg.data_key))


@lru_cache(maxsize=1)
def get_default_cipher() -> AnyCipher:
    return build_cipher()


@lru_cache(maxsize=1)
def get_default_blind_index() -> BlindIndex | None:
    return build_blind_index()


def new_data_key() -> str:
    """Convenience for `python -m app.scripts.create_admin` and operators."""
    import os

    return base64.urlsafe_b64encode(os.urandom(32)).decode()
