"""Roles, the permission matrix, and the MFA guarantee.

The point of these tests is not "the endpoint returns 200". It is that a support admin
cannot quietly become a user administrator because a route forgot a check, and that no
code path mints an admin token without a verified TOTP code.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.mfa import generate_secret, totp_now
from app.core.security import hash_password
from app.db.models import AdminUser


@pytest.fixture()
def new_admin_payload():
    return {"email": "second@example.com", "password": "admin-password-2", "role": "support_admin"}


def test_identity_lists_permissions(client, make_admin):
    founder = make_admin(role="founder")
    body = client.get("/admin/me", headers=founder["headers"]).json()
    assert body["role"] == "founder"
    assert {"admins:write", "emergency:access", "users:write"} <= set(body["permissions"])


@pytest.mark.parametrize(
    "role,expected",
    [("founder", 201), ("platform_admin", 403), ("support_admin", 403)],
)
def test_only_a_founder_creates_administrators(client, make_admin, new_admin_payload, role, expected):
    admin = make_admin(role=role)
    response = client.post("/admin/admins", json=new_admin_payload, headers=admin["headers"])
    assert response.status_code == expected, response.text
    if expected == 201:
        body = response.json()
        assert body["role"] == "support_admin"
        # The secret is returned exactly once, at creation.
        assert body["totp_secret"]
        assert body["otpauth_url"].startswith("otpauth://totp/")


def test_created_administrator_can_sign_in_with_its_secret(client, make_admin, new_admin_payload):
    founder = make_admin(role="founder")
    created = client.post("/admin/admins", json=new_admin_payload, headers=founder["headers"]).json()

    login = client.post(
        "/admin/auth/token",
        json={
            "email": new_admin_payload["email"],
            "password": new_admin_payload["password"],
            "totp_code": totp_now(created["totp_secret"]),
        },
    )
    assert login.status_code == 200, login.text
    identity = client.get("/admin/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert identity["role"] == "support_admin"


def test_support_admin_is_read_only(client, make_user, make_admin):
    target = make_user()
    support = make_admin(role="support_admin")

    assert client.get("/admin/users", headers=support["headers"]).status_code == 200
    assert client.get("/admin/stats", headers=support["headers"]).status_code == 200
    assert client.get("/admin/audit", headers=support["headers"]).status_code == 200

    blocked = client.post(
        f"/admin/users/{target['id']}/status", json={"is_active": False}, headers=support["headers"]
    )
    assert blocked.status_code == 403
    assert "users:write" in blocked.json()["error"]["message"]
    assert client.get("/admin/health", headers=support["headers"]).status_code == 403
    assert client.get("/admin/admins", headers=support["headers"]).status_code == 403


def test_platform_admin_manages_users_but_not_administrators(client, make_user, make_admin):
    target = make_user()
    platform = make_admin(role="platform_admin")

    disabled = client.post(
        f"/admin/users/{target['id']}/status", json={"is_active": False}, headers=platform["headers"]
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    assert client.get("/admin/admins", headers=platform["headers"]).status_code == 200
    assert client.get("/admin/health", headers=platform["headers"]).status_code == 200
    blocked = client.post(
        "/admin/admins",
        json={"email": "x@example.com", "password": "admin-password-3", "role": "founder"},
        headers=platform["headers"],
    )
    assert blocked.status_code == 403


def test_the_last_founder_cannot_be_demoted_or_disabled(client, make_admin):
    founder = make_admin(role="founder")

    demote = client.patch(
        f"/admin/admins/{founder['id']}/role", json={"role": "support_admin"}, headers=founder["headers"]
    )
    assert demote.status_code == 409

    disable = client.post(
        f"/admin/admins/{founder['id']}/status", json={"is_active": False}, headers=founder["headers"]
    )
    assert disable.status_code == 409


def test_a_second_founder_can_demote_the_first(client, make_admin):
    first = make_admin(role="founder")
    second = make_admin(role="founder")
    response = client.patch(
        f"/admin/admins/{first['id']}/role", json={"role": "platform_admin"}, headers=second["headers"]
    )
    assert response.status_code == 200
    assert response.json()["role"] == "platform_admin"


def test_admin_token_requires_a_valid_totp_code(client, session_factory):
    email = "mfa@example.com"
    password = "admin-password-4"
    secret = generate_secret()
    with session_factory() as session:
        session.add(
            AdminUser(
                email=email,
                password_hash=hash_password(password),
                mfa_secret=secret,
                role="founder",
                is_active=True,
            )
        )
        session.commit()

    assert client.post("/admin/auth/token", json={"email": email, "password": password, "totp_code": "000000"}).status_code == 401
    # A password alone is not enough either: the field is required by the contract.
    assert client.post("/admin/auth/token", json={"email": email, "password": password}).status_code == 422
    assert client.post(
        "/admin/auth/token", json={"email": email, "password": password, "totp_code": totp_now(secret)}
    ).status_code == 200


def test_an_admin_cannot_exist_without_an_mfa_secret(session_factory):
    with session_factory() as session:
        session.add(AdminUser(email="no-mfa@example.com", password_hash=hash_password("x" * 12), role="founder"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_failed_admin_logins_are_audited_and_surfaced(client, make_admin):
    founder = make_admin(role="founder")
    client.post("/admin/auth/token", json={"email": founder["email"], "password": "wrong-password", "totp_code": "000000"})

    security = client.get("/admin/security", headers=founder["headers"]).json()
    assert security["failed_admin_logins_24h"] >= 1
    assert any(event["action"] == "admin.login_failed" for event in security["recent_events"])


def test_emergency_access_is_founder_only_and_records_its_reason(client, make_admin):
    founder = make_admin(role="founder")
    granted = client.post(
        "/admin/emergency/access", json={"reason": "founder locked out of the billing console"}, headers=founder["headers"]
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["scope"] == "emergency"
    assert granted.json()["expires_in"] == 900

    events = client.get("/admin/audit", headers=founder["headers"]).json()["items"]
    assert any(
        event["action"] == "admin.emergency_access"
        and event["detail"].get("reason", "").startswith("founder locked out")
        for event in events
    )

    platform = make_admin(role="platform_admin")
    denied = client.post(
        "/admin/emergency/access", json={"reason": "curious about the billing console"}, headers=platform["headers"]
    )
    assert denied.status_code == 403


def test_health_and_analytics_report_real_counts(client, make_user, create_memory, make_admin):
    owner = make_user()
    create_memory(owner["headers"])
    founder = make_admin(role="founder")

    health = client.get("/admin/health", headers=founder["headers"]).json()
    assert health["status"] == "ok"
    assert health["database"] == "ok"
    assert health["admins_active"] >= 1

    analytics = client.get("/admin/analytics", params={"days": 7}, headers=founder["headers"]).json()
    assert analytics["window_days"] == 7
    assert sum(point["memories"] for point in analytics["points"]) >= 1
