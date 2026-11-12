"""Auth surface: audience separation, MFA gate, no account enumeration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.mfa import totp_now
from app.core.security import ADMIN_AUDIENCE, USER_AUDIENCE, create_access_token


def test_register_rejects_short_password(client):
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert response.status_code == 422


def test_register_rejects_bad_email(client):
    response = client.post("/api/auth/register", json={"email": "not-an-email", "password": "correct-horse-battery"})
    assert response.status_code == 422


def test_duplicate_email_is_conflict(client, make_user):
    user = make_user()
    response = client.post(
        "/api/auth/register", json={"email": user["email"].upper(), "password": "another-good-pass"}
    )
    assert response.status_code == 409


def test_login_failures_are_indistinguishable(client, make_user):
    user = make_user()
    wrong_password = client.post("/api/auth/token", json={"email": user["email"], "password": "totally-wrong-1"})
    unknown_user = client.post("/api/auth/token", json={"email": "ghost@example.com", "password": "totally-wrong-1"})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_tampered_token_rejected(client, make_user):
    user = make_user()
    token = user["token"]
    tampered = token[:-3] + ("abc" if not token.endswith("abc") else "xyz")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_expired_token_rejected(client, make_user):
    user = make_user()
    expired = create_access_token(user["id"], audience=USER_AUDIENCE, ttl_seconds=-60)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_disabled_user_is_locked_out(client, make_user, make_admin):
    user = make_user()
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 200

    admin = make_admin()
    disable = client.post(
        f"/admin/users/{user['id']}/status", json={"is_active": False}, headers=admin["headers"]
    )
    assert disable.status_code == 200
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401

    login = client.post("/api/auth/token", json={"email": user["email"], "password": user["password"]})
    assert login.status_code == 403


def test_user_token_cannot_touch_admin_routes(client, make_user):
    user = make_user()
    for path in ("/admin/stats", "/admin/users", "/admin/audit"):
        assert client.get(path, headers=user["headers"]).status_code == 401


def test_admin_token_cannot_touch_user_routes(client, make_admin, create_memory):
    admin = make_admin()
    assert client.get("/api/auth/me", headers=admin["headers"]).status_code == 401
    assert client.get("/api/memories", headers=admin["headers"]).status_code == 401


def test_admin_token_without_mfa_claim_is_rejected(client, make_admin):
    admin = make_admin()
    # Correctly signed, right audience, but the MFA claim is false: still refused.
    forged = create_access_token(admin["id"], audience=ADMIN_AUDIENCE, mfa=False)
    response = client.get("/admin/stats", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_admin_login_requires_valid_totp(client, make_admin, session_factory):
    from app.db.models import AdminUser
    from app.core.security import hash_password

    email, password = "totp-admin@example.com", "admin-password-1"
    with session_factory() as session:
        session.add(
            AdminUser(
                email=email,
                password_hash=hash_password(password),
                mfa_secret="JBSWY3DPEHPK3PXP",
                role="founder",
                is_active=True,
            )
        )
        session.commit()

    bad = client.post("/admin/auth/token", json={"email": email, "password": password, "totp_code": "000000"})
    assert bad.status_code == 401

    good = client.post(
        "/admin/auth/token",
        json={"email": email, "password": password, "totp_code": totp_now("JBSWY3DPEHPK3PXP")},
    )
    assert good.status_code == 200
