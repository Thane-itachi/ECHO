"""Where the encrypted bytes of a document actually live.

Two stores, one contract. A long-running deploy and the test suite write to a
directory. A serverless deploy cannot: the filesystem is a scratch directory that the
next cold start does not share, so the bytes go to object storage (Vercel Blob) and the
database keeps only metadata, exactly as before.

Both stores see ciphertext only. `DocumentService` encrypts before calling `put` and
decrypts after `get`, so a bucket full of documents is as useful as an encrypted
database without the master key.

The Blob wire format is the documented REST shape, not the JS SDK: upload is a `PUT` to
`https://blob.vercel-storage.com/?pathname=<key>` carrying the access mode in
`x-vercel-blob-access`, and a private blob is read from the store's own
`<store>.private.blob.vercel-storage.com` host with the same bearer token. That host
answers `403` without a token, which is the point of asking for a private store.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.core.config import settings


class StorageError(RuntimeError):
    """The bytes could not be stored or fetched, and the caller should say so."""


class DocumentStore(Protocol):
    kind: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStore:
    """A directory on this machine. Development, docker, tests."""

    kind = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        root = self.root.resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            # A generated key never looks like this; a hand-written one might.
            raise StorageError("invalid storage key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self.path_for(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)


class BlobStore:
    """Vercel Blob, spoken directly over HTTPS so the backend needs no Node SDK."""

    kind = "vercel-blob"
    API = "https://blob.vercel-storage.com"

    def __init__(
        self,
        token: str,
        store_id: str | None = None,
        *,
        api: str = API,
        download_host: str | None = None,
        download_base: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not token:
            raise StorageError("BLOB_READ_WRITE_TOKEN is required for the Vercel Blob store")
        self.token = token
        self.store_id = store_id
        self.api = api.rstrip("/")
        self.download_host = download_host or self._derive_host(store_id)
        # Overridable so a test can point reads at a local stub instead of the CDN.
        self.download_base = download_base or (
            f"https://{self.download_host}" if self.download_host else None
        )
        self.timeout = timeout

    @staticmethod
    def _derive_host(store_id: str | None) -> str | None:
        """`store_EbB7OE...` is served from `ebb7oe....private.blob.vercel-storage.com`."""
        if not store_id:
            return None
        bare = store_id[6:] if store_id.startswith("store_") else store_id
        return f"{bare.lower()}.private.blob.vercel-storage.com"

    # ------------------------------------------------------------------ calls
    def _send(self, request: Request) -> bytes:
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed https hosts
                return response.read()
        except HTTPError as exc:
            if exc.code in (403, 404):
                raise FileNotFoundError(request.full_url) from exc
            detail = exc.read()[:300].decode("utf-8", "replace")
            raise StorageError(f"blob store returned {exc.code}: {detail}") from exc
        except URLError as exc:
            raise StorageError(f"could not reach the blob store: {exc.reason}") from exc

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}", "x-api-version": "12", **extra}

    # ------------------------------------------------------------------ contract
    def put(self, key: str, data: bytes) -> None:
        url = f"{self.api}/?{urlencode({'pathname': key})}"
        self._send(
            Request(
                url,
                data=data,
                method="PUT",
                headers=self._headers(
                    **{
                        "x-content-type": "application/octet-stream",
                        "x-vercel-blob-access": "private",
                        "x-add-random-suffix": "0",
                    }
                ),
            )
        )

    def get(self, key: str) -> bytes:
        if not self.download_base:
            raise StorageError("the blob store host is unknown: set ECHO_BLOB_DOWNLOAD_HOST")
        # `?cb=` because the private host is behind a CDN: without it a re-upload under
        # the same key can serve the previous bytes.
        url = f"{self.download_base}/{quote(key)}?cb={uuid.uuid4().hex}"
        return self._send(Request(url, headers=self._headers()))

    def delete(self, key: str) -> None:
        url = f"{self.api}/?{urlencode({'pathname': key})}"
        try:
            self._send(Request(url, method="DELETE", headers=self._headers()))
        except FileNotFoundError:
            # Already gone is the outcome the caller wanted.
            return


def build_document_store() -> DocumentStore:
    """The configured store, or the local directory when nothing else is asked for."""
    if settings.storage_backend == "vercel-blob":
        return BlobStore(
            settings.blob_read_write_token or "",
            settings.blob_store_id,
            download_host=settings.blob_download_host,
            timeout=settings.blob_timeout_seconds,
        )
    return LocalStore(settings.storage_dir)


def describe(store: DocumentStore) -> str:
    if isinstance(store, BlobStore):
        return f"vercel blob (store {settings.blob_store_id or 'from token'})"
    return f"local directory {Path(store.root)}"  # type: ignore[attr-defined]


def store_from_json(payload: str) -> dict:
    """Small helper kept for tests that assert on the upload response shape."""
    return json.loads(payload)
