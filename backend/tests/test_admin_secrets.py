"""Administrators' TOTP seeds are sealed, not ordinary account fields.

MFA that ships as a plaintext column is MFA until someone reads the backups. These
tests hold the line: the column is ciphertext, the derivation is not any user's content
key, and an upgrade from a plaintext row keeps administrators able to sign in.
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.crypto import CipherError, ContentCipher, new_data_key
from app.core.mfa import generate_secret, totp_now
from app.core.security import hash_password
from app.db.models import AdminUser
from app.main import create_app

PASSWORD = "admin-password-1"


def _cipher() -> ContentCipher:
    return ContentCipher(base64.urlsafe_b64decode(new_data_key()))


def _raw_secret(session_factory) -> str:
    with session_factory() as session:
        return session.execute(text("SELECT mfa_secret FROM admin_users")).scalar_one()


def test_the_totp_seed_is_ciphertext_in_the_database(session_factory):
    cipher = _cipher()
    secret = generate_secret()
    with TestClient(create_app(session_factory=session_factory, cipher=cipher)) as client:
        with session_factory() as session:
            session.add(
                AdminUser(
                    email="founder@echo.test",
                    password_hash=hash_password(PASSWORD),
                    mfa_secret=secret,
                    role="founder",
                )
            )
            session.commit()

        stored = _raw_secret(session_factory)
        assert stored.startswith("s1:")
        assert secret not in stored
        # The application reads it back without knowing a key exists...
        assert cipher.unseal(stored) == secret

        # ...and login still works, which is the whole point of the second factor.
        signed_in = client.post(
            "/admin/auth/token",
            json={"email": "founder@echo.test", "password": PASSWORD, "totp_code": totp_now(secret)},
        )
        assert signed_in.status_code == 200, signed_in.text


def test_a_sealed_secret_is_not_reachable_with_a_user_content_key(session_factory):
    cipher = _cipher()
    sealed = cipher.seal(generate_secret())
    # Different derivation: a bug that reads one user's memory cannot be replayed here.
    assert cipher.can_decrypt(sealed, "some-user-id") is False
    with pytest.raises(CipherError):
        cipher.decrypt(sealed, "some-user-id")


def test_a_legacy_plaintext_row_still_signs_in(session_factory):
    """An upgrade must not lock an administrator out before the migration runs."""
    cipher = _cipher()
    secret = generate_secret()
    with TestClient(create_app(session_factory=session_factory, cipher=cipher)) as client:
        # Written the way the old schema wrote it: raw SQL, no sealing.
        with session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO admin_users (id, email, password_hash, mfa_secret, role,"
                    " is_active, created_at, updated_at)"
                    " VALUES ('legacy-1', 'legacy@echo.test', :pw, :secret, 'founder', 1,"
                    " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"pw": hash_password(PASSWORD), "secret": secret},
            )
            session.commit()

        assert cipher.is_sealed(_raw_secret(session_factory)) is False
        response = client.post(
            "/admin/auth/token",
            json={"email": "legacy@echo.test", "password": PASSWORD, "totp_code": totp_now(secret)},
        )
        assert response.status_code == 200, response.text


def test_resealing_a_legacy_row_keeps_the_same_secret(session_factory):
    cipher = _cipher()
    secret = generate_secret()
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO admin_users (id, email, password_hash, mfa_secret, role,"
                " is_active, created_at, updated_at)"
                " VALUES ('legacy-2', 'legacy2@echo.test', :pw, :secret, 'founder', 1,"
                " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            ),
            {"pw": hash_password(PASSWORD), "secret": secret},
        )
        session.commit()

    # What the migration does, and what `rotate_data_key` does: seal, then read back.
    with session_factory() as session:
        row = session.execute(text("SELECT id, mfa_secret FROM admin_users")).one()
        sealed = cipher.seal(row.mfa_secret)
        session.execute(
            text("UPDATE admin_users SET mfa_secret = :sealed WHERE id = :id"),
            {"sealed": sealed, "id": row.id},
        )
        session.commit()

    stored = _raw_secret(session_factory)
    assert stored.startswith("s1:")
    assert cipher.unseal(stored) == secret
    # The secret an authenticator app already has keeps working.
    assert totp_now(cipher.unseal(stored)) == totp_now(secret)
