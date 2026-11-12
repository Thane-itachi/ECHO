"""Encryption decision (fix #2): content is encrypted at rest *and* search still works."""
from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.crypto import CipherError, ContentCipher, NullCipher, new_data_key
from app.db.models import Memory
from app.main import create_app

SECRET_TEXT = "the safe combination is 44-19-07"


@pytest.fixture()
def encrypted_client(session_factory):
    cipher = ContentCipher(base64.urlsafe_b64decode(new_data_key()))
    with TestClient(create_app(session_factory=session_factory, cipher=cipher)) as client:
        yield client


def test_content_is_ciphertext_in_the_database(encrypted_client, session_factory):
    registered = encrypted_client.post(
        "/api/auth/register", json={"email": "enc@example.com", "password": "correct-horse-battery"}
    )
    token = encrypted_client.post(
        "/api/auth/token", json={"email": "enc@example.com", "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert registered.status_code == 201

    created = encrypted_client.post(
        "/api/memories", json={"title": "Safe code", "content": SECRET_TEXT}, headers=headers
    )
    assert created.status_code == 201
    # The API returns plaintext to the owner...
    assert created.json()["content"] == SECRET_TEXT

    with session_factory() as session:
        row = session.scalars(select(Memory)).one()
        assert row.content_enc.startswith("f1:")
        assert SECRET_TEXT not in row.content_enc
        # The documented tradeoff, asserted rather than assumed: search reads a derived
        # plaintext index, so searching never requires decrypting another user's rows.
        # Ciphertext is the only copy of the body itself.
        assert row.search_text == f"Safe code\n{SECRET_TEXT}".lower()


def test_search_still_works_over_encrypted_rows(encrypted_client):
    encrypted_client.post("/api/auth/register", json={"email": "s@example.com", "password": "correct-horse-battery"})
    token = encrypted_client.post(
        "/api/auth/token", json={"email": "s@example.com", "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    encrypted_client.post("/api/memories", json={"title": "Safe code", "content": SECRET_TEXT}, headers=headers)

    hits = encrypted_client.get("/api/memories", params={"q": "combination"}, headers=headers).json()
    assert hits["total"] == 1
    assert hits["items"][0]["content"] == SECRET_TEXT


def test_ciphertext_is_bound_to_its_owner():
    cipher = ContentCipher(os.urandom(32))
    blob = cipher.encrypt(SECRET_TEXT, "user-a")
    assert cipher.decrypt(blob, "user-a") == SECRET_TEXT
    with pytest.raises(CipherError):
        cipher.decrypt(blob, "user-b")


def test_null_cipher_refuses_when_production_style():
    cipher = NullCipher(allow=False)
    with pytest.raises(CipherError):
        cipher.encrypt("plain", "user-a")


def test_cipher_is_plaintext_passthrough_only_without_a_key():
    from dataclasses import replace

    from app.core.config import settings as base
    from app.core.crypto import build_cipher

    assert isinstance(build_cipher(replace(base, data_key=None, env="development")), NullCipher)


def test_cipher_refuses_plaintext_in_production():
    from dataclasses import replace

    from app.core.config import settings as base
    from app.core.crypto import build_cipher

    cipher = build_cipher(replace(base, data_key=None, env="production"))
    assert isinstance(cipher, NullCipher)
    with pytest.raises(CipherError):
        cipher.encrypt("plain", "user-a")


def test_cipher_encrypts_once_a_key_is_configured():
    from dataclasses import replace

    from app.core.config import settings as base
    from app.core.crypto import build_cipher

    cipher = build_cipher(replace(base, data_key=new_data_key(), env="production"))
    assert isinstance(cipher, ContentCipher)
    blob = cipher.encrypt(SECRET_TEXT, "user-a")
    assert SECRET_TEXT not in blob
    assert cipher.decrypt(blob, "user-a") == SECRET_TEXT
