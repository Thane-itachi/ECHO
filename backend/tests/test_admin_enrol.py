"""Enrolment links: the only way an administrator account is born.

The properties under test are the ones that make this safe to hand to someone else:
the link is single-use, it expires, it yields no session until the holder proves they
can produce a code from the secret they were shown, and the password is chosen by the
account holder rather than known by whoever issued the link.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.admin import enrolment
from app.core.mfa import otpauth_url, totp_now
from app.db.models import AdminInvite, AdminUser, AuditLog
from app.core.time import utcnow


def _issue(session_factory, email="new-admin@example.com", role="founder", ttl_hours=72):
    with session_factory() as session:
        invite, token = enrolment.issue_invite(
            session, email=email, role=role, issued_by=None, ttl_hours=ttl_hours
        )
        return invite.id, token


def test_link_shows_who_it_is_for(client, session_factory):
    _, token = _issue(session_factory, email="terdoo@example.com", role="founder")

    response = client.get(f"/admin/auth/enrol/{token}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "terdoo@example.com"
    assert body["role"] == "founder"
    assert body["account_exists"] is False


def test_enrolment_sets_password_and_returns_a_secret_once(client, session_factory):
    _, token = _issue(session_factory)

    response = client.post(f"/admin/auth/enrol/{token}", json={"password": "chosen-by-me-2026"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totp_secret"]
    assert body["otpauth_url"].startswith("otpauth://totp/")
    assert body["qr_data_uri"].startswith("data:image/png;base64,")
    # the password is never echoed back
    assert "password" not in body

    with session_factory() as session:
        account = session.scalars(
            select(AdminUser).where(AdminUser.email == "new-admin@example.com")
        ).one()
        assert account.role == "founder"
        assert account.is_active is True
        # the secret the caller was shown is the one that is stored
        assert account.mfa_secret == body["totp_secret"]


def test_no_session_until_the_secret_is_proven(client, session_factory):
    _, token = _issue(session_factory)
    granted = client.post(
        f"/admin/auth/enrol/{token}", json={"password": "chosen-by-me-2026"}
    ).json()
    secret = granted["totp_secret"]

    # a wrong code cannot burn the link
    wrong = client.post(f"/admin/auth/enrol/{token}/confirm", json={"totp_code": "000000"})
    assert wrong.status_code == 401, wrong.text

    # a password-only sign-in is impossible, as everywhere in this console
    no_mfa = client.post(
        "/admin/auth/token",
        json={"email": "new-admin@example.com", "password": "chosen-by-me-2026", "totp_code": "000000"},
    )
    assert no_mfa.status_code == 401

    confirmed = client.post(
        f"/admin/auth/enrol/{token}/confirm", json={"totp_code": totp_now(secret)}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["email"] == "new-admin@example.com"

    signed_in = client.post(
        "/admin/auth/token",
        json={
            "email": "new-admin@example.com",
            "password": "chosen-by-me-2026",
            "totp_code": totp_now(secret),
        },
    )
    assert signed_in.status_code == 200, signed_in.text
    token_body = signed_in.json()
    me = client.get("/admin/me", headers={"Authorization": f"Bearer {token_body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "founder"


def test_link_is_single_use(client, session_factory):
    _, token = _issue(session_factory)
    granted = client.post(
        f"/admin/auth/enrol/{token}", json={"password": "chosen-by-me-2026"}
    ).json()
    client.post(
        f"/admin/auth/enrol/{token}/confirm",
        json={"totp_code": totp_now(granted["totp_secret"])},
    )

    again = client.get(f"/admin/auth/enrol/{token}")
    assert again.status_code == 409, again.text

    reuse = client.post(f"/admin/auth/enrol/{token}", json={"password": "another-password-1"})
    assert reuse.status_code == 409, reuse.text


def test_expired_link_is_refused(client, session_factory):
    invite_id, token = _issue(session_factory)
    with session_factory() as session:
        invite = session.get(AdminInvite, invite_id)
        invite.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()

    response = client.get(f"/admin/auth/enrol/{token}")
    assert response.status_code == 409
    assert "expired" in response.json()["error"]["message"]


def test_unknown_and_malformed_tokens_are_refused(client):
    assert client.get("/admin/auth/enrol/not-a-real-token").status_code == 404
    assert client.post("/admin/auth/enrol/x", json={"password": "long-enough-123"}).status_code == 404


def test_short_password_is_refused_before_anything_is_created(client, session_factory):
    _, token = _issue(session_factory)

    response = client.post(f"/admin/auth/enrol/{token}", json={"password": "short"})

    assert response.status_code == 422
    with session_factory() as session:
        assert (
            session.scalars(select(AdminUser).where(AdminUser.email == "new-admin@example.com")).first()
            is None
        )


def test_reissuing_retires_the_previous_link(client, session_factory):
    _, first = _issue(session_factory)
    _, second = _issue(session_factory)

    assert client.get(f"/admin/auth/enrol/{first}").status_code == 404
    assert client.get(f"/admin/auth/enrol/{second}").status_code == 200


def test_link_resets_an_existing_admin_with_a_fresh_secret(client, session_factory, make_admin):
    existing = make_admin(email="locked-out@example.com", role="founder")
    _, token = _issue(session_factory, email="locked-out@example.com", role="founder")

    granted = client.post(
        f"/admin/auth/enrol/{token}", json={"password": "a-brand-new-password"}
    ).json()

    assert granted["totp_secret"] != existing["secret"]
    # the old secret no longer works
    stale = client.post(
        "/admin/auth/token",
        json={
            "email": "locked-out@example.com",
            "password": "a-brand-new-password",
            "totp_code": totp_now(existing["secret"]),
        },
    )
    assert stale.status_code == 401
    # the new one does, once confirmed
    client.post(
        f"/admin/auth/enrol/{token}/confirm", json={"totp_code": totp_now(granted["totp_secret"])}
    )
    fresh = client.post(
        "/admin/auth/token",
        json={
            "email": "locked-out@example.com",
            "password": "a-brand-new-password",
            "totp_code": totp_now(granted["totp_secret"]),
        },
    )
    assert fresh.status_code == 200


def test_the_audit_trail_records_the_enrolment_but_never_the_token(client, session_factory):
    _, token = _issue(session_factory, email="audited@example.com")
    granted = client.post(
        f"/admin/auth/enrol/{token}", json={"password": "chosen-by-me-2026"}
    ).json()
    client.post(
        f"/admin/auth/enrol/{token}/confirm", json={"totp_code": totp_now(granted["totp_secret"])}
    )

    with session_factory() as session:
        actions = [row.action for row in session.scalars(select(AuditLog)).all()]
        assert "admin.invite_issued" in actions
        assert "admin.enrolment_started" in actions
        assert "admin.enrolled" in actions
        # the raw token must never be written down anywhere
        for row in session.scalars(select(AuditLog)).all():
            assert token not in str(row.detail)


def test_a_founder_can_mint_a_link_from_the_console(client, make_admin):
    founder = make_admin(role="founder")

    created = client.post(
        "/admin/admins/invites",
        json={"email": "colleague@example.com", "role": "support_admin"},
        headers=founder["headers"],
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["enrol_path"].startswith("/admin/enrol?token=")
    # and that link actually works
    info = client.get(f"/admin/auth/enrol/{body['token']}")
    assert info.status_code == 200
    assert info.json()["email"] == "colleague@example.com"


def test_a_support_admin_cannot_mint_links(client, make_admin):
    support = make_admin(role="support_admin")

    response = client.post(
        "/admin/admins/invites",
        json={"email": "someone@example.com"},
        headers=support["headers"],
    )

    assert response.status_code == 403


def test_otpauth_url_matches_the_secret(client, session_factory):
    _, token = _issue(session_factory)
    granted = client.post(
        f"/admin/auth/enrol/{token}", json={"password": "chosen-by-me-2026"}
    ).json()
    assert granted["otpauth_url"] == otpauth_url(granted["totp_secret"], "new-admin@example.com")
