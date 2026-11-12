"""Document bytes: the local directory, and the object store a serverless deploy needs.

The Blob store talks to a real HTTP API, so the transport is a stub server here rather
than a mock object: the assertions are about the request ECHO actually makes (private
access mode, the pathname parameter, the bearer token, the read host) and about what it
does with a 403, which is the interesting case, because that is what a token-less read
of a private store looks like.
"""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.services.document_storage import BlobStore, LocalStore, StorageError, build_document_store

TOKEN = "vercel_blob_rw_test_token"
STORE_ID = "store_AbCdEf123456"


# --------------------------------------------------------------- local store


def test_local_store_round_trip(tmp_path):
    store = LocalStore(tmp_path)
    store.put("owner-a/one", b"ciphertext")
    assert (tmp_path / "owner-a" / "one").read_bytes() == b"ciphertext"
    assert store.get("owner-a/one") == b"ciphertext"
    store.delete("owner-a/one")
    assert not (tmp_path / "owner-a" / "one").exists()
    # Deleting twice is not an error: a retried delete should be harmless.
    store.delete("owner-a/one")
    with pytest.raises(FileNotFoundError):
        store.get("owner-a/one")


# ---------------------------------------------------------------- blob store


class BlobHandler(BaseHTTPRequestHandler):
    """The three calls the store makes, recorded for assertions."""

    calls: list[dict] = []
    objects: dict[str, bytes] = {}

    def _record(self, method: str) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        parsed = urlparse(self.path)
        key = (parse_qs(parsed.query).get("pathname") or [parsed.path.lstrip("/")])[0]
        type(self).calls.append(
            {
                "method": method,
                "path": parsed.path,
                "query": parsed.query,
                "host": self.headers.get("Host"),
                "key": key,
                "authorization": self.headers.get("authorization"),
                "access": self.headers.get("x-vercel-blob-access"),
                "api_version": self.headers.get("x-api-version"),
                "body": body,
            }
        )
        return key

    def do_PUT(self):  # noqa: N802 - the HTTP verb is the name
        key = self._record("PUT")
        type(self).objects[key] = self.rfile  # not used; body recorded above
        type(self).objects[key] = self.calls[-1]["body"]
        payload = json.dumps({"url": f"https://x/{key}", "pathname": key}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        key = self._record("GET")
        blob = type(self).objects.get(key)
        if blob is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"not_found"}}')
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_DELETE(self):  # noqa: N802
        key = self._record("DELETE")
        existed = type(self).objects.pop(key, None) is not None
        payload = b"null" if existed else b'{"error":{"code":"not_found"}}'
        self.send_response(200 if existed else 404)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep the test output clean
        pass


@pytest.fixture()
def blob_server():
    BlobHandler.calls = []
    BlobHandler.objects = {}
    server = HTTPServer(("127.0.0.1", 0), BlobHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield BlobHandler, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def a_store(base: str) -> BlobStore:
    return BlobStore(TOKEN, STORE_ID, api=base, download_base=base, timeout=5.0)


def test_an_upload_is_private_and_keeps_the_key_it_was_given(blob_server):
    handler, base = blob_server
    store = a_store(base)
    store.put("owner-a/deadbeef", b"sealed bytes")

    upload = handler.calls[0]
    assert upload["method"] == "PUT"
    assert upload["key"] == "owner-a/deadbeef"
    assert upload["access"] == "private"  # a private store refuses a public upload
    assert upload["authorization"] == f"Bearer {TOKEN}"
    assert upload["api_version"] == "12"
    assert upload["body"] == b"sealed bytes"


def test_a_download_goes_to_the_private_host_with_a_cache_buster(blob_server):
    handler, base = blob_server
    handler.objects["owner-a/one"] = b"sealed bytes"
    store = a_store(base)

    assert store.get("owner-a/one") == b"sealed bytes"
    read = handler.calls[-1]
    assert read["method"] == "GET"
    assert read["authorization"] == f"Bearer {TOKEN}"
    # The private store host is behind a CDN: without a unique parameter a re-upload
    # under the same key can serve the previous bytes.
    assert "cb=" in read["query"]


def test_a_missing_blob_is_a_file_not_found_so_the_route_can_say_404(blob_server):
    _handler, base = blob_server
    store = a_store(base)
    with pytest.raises(FileNotFoundError):
        store.get("owner-a/never-existed")


def test_a_forbidden_read_is_treated_as_missing_not_as_a_crash(blob_server):
    """A revoked token and a deleted object both mean "you cannot have this"."""

    class Forbidden(BlobHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"forbidden"}}')

    server = HTTPServer(("127.0.0.1", 0), Forbidden)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        store = BlobStore(
            TOKEN,
            STORE_ID,
            api=f"http://127.0.0.1:{server.server_port}",
            download_base=f"http://127.0.0.1:{server.server_port}",
        )
        with pytest.raises(FileNotFoundError):
            store.get("owner-a/one")
    finally:
        server.shutdown()
        server.server_close()


def test_a_failure_is_loud_rather_than_silent(blob_server):
    _handler, base = blob_server
    with pytest.raises(StorageError):
        # No token is not a runtime surprise: it refuses to exist at all, rather than
        # accept uploads and lose them one at a time.
        BlobStore("", STORE_ID, api=base, download_base=base)
    dead = BlobStore(TOKEN, STORE_ID, api="http://127.0.0.1:9", download_base=base, timeout=1.0)
    with pytest.raises(StorageError):
        dead.put("owner-a/one", b"x")


def test_deleting_something_already_gone_is_not_an_error(blob_server):
    _handler, base = blob_server
    store = a_store(base)
    store.delete("owner-a/missing")  # 404 from the store: the caller wanted it gone


def test_the_download_host_is_derived_from_the_store_id():
    store = BlobStore(TOKEN, "store_AbCdEf123456")
    assert store.download_host == "abcdef123456.private.blob.vercel-storage.com"


def test_the_configured_backend_decides_which_store_is_built(monkeypatch, tmp_path):
    import app.services.document_storage as module

    monkeypatch.setattr(module, "settings", replace(settings, storage_backend="local", storage_dir=str(tmp_path)))
    assert build_document_store().kind == "local"

    monkeypatch.setattr(
        module,
        "settings",
        replace(settings, storage_backend="vercel-blob", blob_read_write_token=TOKEN, blob_store_id=STORE_ID),
    )
    assert build_document_store().kind == "vercel-blob"
