"""Documents: encrypted at rest, owner-scoped, size-capped."""
from __future__ import annotations

import pathlib

import pytest

from app.core.crypto import NullCipher
from app.core.errors import PayloadTooLarge
from app.services.documents import DocumentService

PAYLOAD = b"Invoice 118 - Bright Foods - 40,000 naira - due in 14 days"


def _upload(client, headers, *, name="invoice.txt", data=PAYLOAD, memory_id=None):
    form = {"memory_id": memory_id} if memory_id else None
    return client.post(
        "/api/documents",
        files={"file": (name, data, "text/plain")},
        data=form,
        headers=headers,
    )


def test_upload_download_and_delete(client, make_user, storage_dir):
    owner = make_user()
    created = _upload(client, owner["headers"])
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["filename"] == "invoice.txt"
    assert document["size_bytes"] == len(PAYLOAD)

    listing = client.get("/api/documents", headers=owner["headers"]).json()
    assert listing["total"] == 1

    download = client.get(f"/api/documents/{document['id']}/download", headers=owner["headers"])
    assert download.status_code == 200
    assert download.content == PAYLOAD

    # At rest the bytes on disk are ciphertext, and no plaintext is anywhere in storage.
    files = [path for path in pathlib.Path(storage_dir).rglob("*") if path.is_file()]
    assert files, "the file should exist on disk"

    deleted = client.delete(f"/api/documents/{document['id']}", headers=owner["headers"])
    assert deleted.status_code == 204
    assert client.get("/api/documents", headers=owner["headers"]).json()["total"] == 0
    assert [path for path in storage_dir.rglob("*") if path.is_file()] == []


def test_document_can_be_attached_to_a_memory(client, make_user, create_memory):
    owner = make_user()
    memory = create_memory(owner["headers"])
    created = _upload(client, owner["headers"], memory_id=memory["id"])
    assert created.status_code == 201
    assert created.json()["memory_id"] == memory["id"]


def test_cannot_attach_to_another_tenants_memory(client, make_user, create_memory):
    alice = make_user()
    bob = make_user()
    alice_memory = create_memory(alice["headers"])
    attempt = _upload(client, bob["headers"], memory_id=alice_memory["id"])
    assert attempt.status_code == 404


def test_documents_are_owner_scoped(client, make_user):
    alice = make_user()
    bob = make_user()
    document = _upload(client, alice["headers"]).json()

    assert client.get("/api/documents", headers=bob["headers"]).json()["total"] == 0
    assert client.get(f"/api/documents/{document['id']}/download", headers=bob["headers"]).status_code == 404
    assert client.delete(f"/api/documents/{document['id']}", headers=bob["headers"]).status_code == 404


def test_empty_upload_is_rejected(client, make_user):
    owner = make_user()
    assert _upload(client, owner["headers"], data=b"").status_code == 413


def test_size_limit_is_enforced(session_factory, tmp_path):
    with session_factory() as session:
        service = DocumentService(
            session, "owner-a", cipher=NullCipher(), storage_dir=tmp_path, max_bytes=8
        )
        with pytest.raises(PayloadTooLarge):
            service.store(filename="big.txt", data=b"0123456789", content_type="text/plain")


def test_at_rest_bytes_are_ciphertext(session_factory, tmp_path):
    """With a real data key, the file on disk is unreadable without it."""
    import os

    from fastapi.testclient import TestClient

    from app.core.crypto import ContentCipher
    from app.main import create_app

    app = create_app(session_factory=session_factory, cipher=ContentCipher(os.urandom(32)))
    storage = tmp_path / "enc-storage"
    storage.mkdir()
    app.state.storage_dir = str(storage)

    with TestClient(app) as client:
        client.post("/api/auth/register", json={"email": "doc@example.com", "password": "correct-horse-battery"})
        token = client.post(
            "/api/auth/token", json={"email": "doc@example.com", "password": "correct-horse-battery"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/documents", files={"file": ("invoice.txt", PAYLOAD, "text/plain")}, headers=headers
        )
        assert created.status_code == 201, created.text
        downloaded = client.get(f"/api/documents/{created.json()['id']}/download", headers=headers)
        assert downloaded.content == PAYLOAD

    blobs = b"".join(path.read_bytes() for path in storage.rglob("*") if path.is_file())
    assert blobs, "encrypted file should exist on disk"
    assert b"Bright Foods" not in blobs
    assert b"naira" not in blobs


def test_storage_key_cannot_escape_the_storage_directory(session_factory, tmp_path):
    with session_factory() as session:
        service = DocumentService(session, "owner-a", cipher=NullCipher(), storage_dir=tmp_path / "root")
        with pytest.raises(PayloadTooLarge):
            service._path("../../etc/passwd")
