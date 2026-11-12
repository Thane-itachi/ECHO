import os

# Must be set before app.core.config is imported for the first time.
os.environ.setdefault("ECHO_ENV", "test")
os.environ.setdefault("ECHO_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ECHO_PASSWORD_ITERATIONS", "1000")  # keep the suite fast, not weaker
os.environ.setdefault("ECHO_USER_JWT_SECRET", "test-user-secret-0123456789abcdef")
os.environ.setdefault("ECHO_ADMIN_JWT_SECRET", "test-admin-secret-0123456789abcdef")

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.mfa import generate_secret, totp_now
from app.core.security import hash_password
from app.db.models import AdminUser, Base
from app.db.session import build_engine, build_session_factory
from app.main import create_app

VALID_PASSWORD = "correct-horse-battery"


@pytest.fixture()
def engine(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path}/echo-test.db")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(engine):
    return build_session_factory(engine)


@pytest.fixture()
def app(session_factory):
    return create_app(session_factory=session_factory)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_user(client):
    def _make(email: str | None = None, password: str = VALID_PASSWORD) -> dict:
        email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        registered = client.post("/api/auth/register", json={"email": email, "password": password})
        assert registered.status_code == 201, registered.text
        body = registered.json()
        token_response = client.post("/api/auth/token", json={"email": email, "password": password})
        assert token_response.status_code == 200, token_response.text
        token = token_response.json()["access_token"]
        return {
            "id": body["id"],
            "email": email,
            "password": password,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make


@pytest.fixture()
def make_admin(client, session_factory):
    def _make(email: str | None = None, password: str = "admin-password-1", mfa_required: bool = True) -> dict:
        email = (email or f"admin-{uuid.uuid4().hex[:8]}@example.com").lower()
        secret = generate_secret()
        with session_factory() as session:
            admin = AdminUser(
                email=email,
                password_hash=hash_password(password),
                mfa_secret=secret,
                mfa_required=mfa_required,
                is_active=True,
            )
            session.add(admin)
            session.commit()
            admin_id = admin.id
        response = client.post(
            "/admin/auth/token",
            json={"email": email, "password": password, "totp_code": totp_now(secret)},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {
            "id": admin_id,
            "email": email,
            "secret": secret,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
            "password": password,
        }

    return _make


@pytest.fixture()
def create_memory(client):
    def _create(headers, **overrides) -> dict:
        payload = {"title": "John borrowed my laptop", "content": "He promised to return it tomorrow."}
        payload.update(overrides)
        response = client.post("/api/memories", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture()
def create_person(client):
    def _create(headers, name: str = "John") -> dict:
        response = client.post("/api/people", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _create
