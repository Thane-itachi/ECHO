"""Key rotation: change the data key without losing a row.

A master key you cannot change is a master key that leaks forever. The rotation window
is `ECHO_DATA_KEY` (encrypts) plus `ECHO_DATA_KEY_PREVIOUS` (decrypts only), and
`rotate_data_key` rewrites what is left. These tests treat that as a promise: after a
rotation, a process holding only the new key reads every memory, every person note,
every document, every queued capture and every admin login.
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.crypto import CipherError, ContentCipher, new_data_key
from app.core.mfa import generate_secret, totp_now
from app.core.security import hash_password
from app.db.models import AdminUser, Job, Memory
from app.main import create_app
from app.services.mailer import CapturingMailer
from tests.support import sign_in
from app.scripts.rotate_data_key import rotate, survey

USER_PASSWORD = "correct-horse-battery"
ADMIN_PASSWORD = "admin-password-1"
MEMORY_TITLE = "John borrowed my laptop"
MEMORY_CONTENT = "He promised to return it tomorrow."
PERSON_NOTES = "Brother-in-law, allergic to peanuts"
CAPTURE_TEXT = "Sarah collected my documents on Friday"
DOCUMENT_BYTES = b"Invoice 118 - Bright Foods - 40,000 naira"


def _key() -> bytes:
    return base64.urlsafe_b64decode(new_data_key())


def _open(session_factory, cipher: ContentCipher, storage_dir):
    app = create_app(session_factory=session_factory, cipher=cipher)
    app.state.mailer = CapturingMailer()
    app.state.storage_dir = str(storage_dir)
    return TestClient(app)


def _seed(session_factory, cipher: ContentCipher, storage_dir) -> dict:
    """Everything ECHO encrypts, written under one key."""
    secret = generate_secret()
    with _open(session_factory, cipher, storage_dir) as client:
        headers = sign_in(client, email="rot@example.com", password=USER_PASSWORD)

        memory = client.post(
            "/api/memories", json={"title": MEMORY_TITLE, "content": MEMORY_CONTENT}, headers=headers
        ).json()
        person = client.post(
            "/api/people", json={"name": "John", "notes": PERSON_NOTES}, headers=headers
        ).json()
        capture = client.post("/api/captures", json={"text": CAPTURE_TEXT}, headers=headers)
        assert capture.status_code == 202, capture.text
        document = client.post(
            "/api/documents",
            files={"file": ("invoice.txt", DOCUMENT_BYTES, "text/plain")},
            headers=headers,
        ).json()

        with session_factory() as session:
            session.add(
                AdminUser(
                    email="rot-admin@echo.test",
                    password_hash=hash_password(ADMIN_PASSWORD),
                    mfa_secret=secret,
                    role="founder",
                )
            )
            session.commit()

    return {
        "headers": headers,
        "memory_id": memory["id"],
        "person_id": person["id"],
        "document_id": document["id"],
        "secret": secret,
    }


def test_a_retired_key_reads_but_never_writes():
    old = ContentCipher(_key())
    rotating = ContentCipher(_key(), (old.keys[0],))

    under_old = old.encrypt(MEMORY_CONTENT, "user-1")
    assert rotating.can_decrypt(under_old, "user-1")
    assert rotating.encrypted_with_current_key(under_old, "user-1") is False
    assert rotating.decrypt(under_old, "user-1") == MEMORY_CONTENT

    under_new = rotating.encrypt(MEMORY_CONTENT, "user-1")
    assert rotating.encrypted_with_current_key(under_new, "user-1")

    # Drop the retired key and the old ciphertext is genuinely gone, not merely hidden.
    with pytest.raises(CipherError):
        ContentCipher(rotating.keys[0]).decrypt(under_old, "user-1")


def test_survey_counts_without_writing_then_rotation_moves_everything(session_factory, tmp_path):
    old_key, new_key = _key(), _key()
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    seeded = _seed(session_factory, ContentCipher(old_key), storage)

    rotating = ContentCipher(new_key, (old_key,))
    with session_factory() as session:
        before = survey(session, cipher=rotating, storage_dir=storage)
        assert (before.memories, before.people, before.proposals) == (1, 1, 0)
        assert before.capture_jobs == 1
        assert before.admin_secrets == 1
        assert before.documents == 1
        assert before.unreadable == []

        # A survey is read-only: the row is still under the retired key.
        title_enc = session.execute(text("SELECT title_enc FROM memories")).scalar_one()
        assert rotating.encrypted_with_current_key(title_enc, _owner(session)) is False

        report = rotate(session, cipher=rotating, storage_dir=storage, apply=True)
        assert report.unreadable == []
        assert report.memories == 1 and report.people == 1
        assert report.capture_jobs == 1 and report.admin_secrets == 1
        assert report.documents == 1

        after = survey(session, cipher=rotating, storage_dir=storage)
        assert after.total() == 0

    # Only the new key now. Everything must still work, including search: the blind
    # index is keyed, so a rotation that forgot to rekey it would silently return nothing.
    fresh = ContentCipher(new_key)
    with _open(session_factory, fresh, storage) as client:
        headers = seeded["headers"]

        hits = client.get("/api/memories", params={"q": "laptop"}, headers=headers).json()
        assert hits["total"] == 1
        assert hits["items"][0]["content"] == MEMORY_CONTENT

        people = client.get("/api/people", params={"q": "peanuts"}, headers=headers).json()
        assert people["total"] == 1
        assert people["items"][0]["notes"] == PERSON_NOTES

        document = client.get(f"/api/documents/{seeded['document_id']}/download", headers=headers)
        assert document.content == DOCUMENT_BYTES

        signed_in = client.post(
            "/admin/auth/token",
            json={
                "email": "rot-admin@echo.test",
                "password": ADMIN_PASSWORD,
                "totp_code": totp_now(seeded["secret"]),
            },
        )
        assert signed_in.status_code == 200, signed_in.text

    with session_factory() as session:
        job = session.scalars(select(Job)).one()
        payload = job.payload
        assert fresh.decrypt(payload["text_enc"], payload["user_id"]) == CAPTURE_TEXT


def test_rotation_without_the_retired_key_refuses_instead_of_destroying(session_factory, tmp_path):
    old_key, new_key = _key(), _key()
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    _seed(session_factory, ContentCipher(old_key), storage)

    with session_factory() as session:
        report = rotate(session, cipher=ContentCipher(new_key), storage_dir=storage, apply=True)
        assert report.unreadable  # it says what it could not read
        # Nothing was overwritten: the original data is still there under the old key.
        memory = session.scalars(select(Memory)).one()
        assert ContentCipher(old_key).decrypt(memory.content_enc, memory.user_id) == MEMORY_CONTENT


def _owner(session) -> str:
    return session.execute(text("SELECT user_id FROM memories")).scalar_one()
