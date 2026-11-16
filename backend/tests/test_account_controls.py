"""The ways in and out of a vault that do not depend on email.

These exist because a deployment can have no mail provider at all: no reset codes, no
verification, no sign-in codes. Being able to change a password from inside the session,
and to delete the account outright, is what keeps such a deployment from being a trap.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.admin import enrolment
from app.db.models import AdminInvite, AdminUser
from app.services.mailer import LogMailer

NEW_PASSWORD = "a-long-new-passphrase"


def test_password_can_be_changed_without_any_email(client, make_user):
    user = make_user()

    changed = client.patch(
        "/api/auth/password",
        json={"current_password": user["password"], "new_password": NEW_PASSWORD},
        headers=user["headers"],
    )
    assert changed.status_code == 200, changed.text

    # The old token is dead: the change bumps credentials_changed_at. The token that comes
    # back is the one that keeps working, so the person is not thrown out of their vault.
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200

    old = client.post("/api/auth/token", json={"email": user["email"], "password": user["password"]})
    assert old.status_code == 401
    new = client.post("/api/auth/token", json={"email": user["email"], "password": NEW_PASSWORD})
    assert new.status_code == 200


def test_changing_a_password_needs_the_current_one(client, make_user):
    user = make_user()
    refused = client.patch(
        "/api/auth/password",
        json={"current_password": "not-it-at-all", "new_password": NEW_PASSWORD},
        headers=user["headers"],
    )
    assert refused.status_code == 401
    # And the old password still works, so a guess changed nothing.
    assert client.post("/api/auth/token", json={"email": user["email"], "password": user["password"]}).status_code == 200


def test_a_weak_new_password_is_refused(client, make_user):
    user = make_user()
    refused = client.patch(
        "/api/auth/password",
        json={"current_password": user["password"], "new_password": "password"},
        headers=user["headers"],
    )
    assert refused.status_code == 422


def test_deleting_a_vault_removes_the_account_and_everything_in_it(client, make_user):
    user = make_user()
    made = client.post(
        "/api/memories",
        json={"title": "Laptop lent to John", "content": "He said next week."},
        headers=user["headers"],
    )
    assert made.status_code == 201
    memory_id = made.json()["id"]

    refused = client.request(
        "DELETE", "/api/auth/account", json={"password": "not-it-at-all"}, headers=user["headers"]
    )
    assert refused.status_code == 401
    assert client.get(f"/api/memories/{memory_id}", headers=user["headers"]).status_code == 200

    deleted = client.request(
        "DELETE", "/api/auth/account", json={"password": user["password"]}, headers=user["headers"]
    )
    assert deleted.status_code == 204
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401
    assert client.post("/api/auth/token", json={"email": user["email"], "password": user["password"]}).status_code == 401


def test_sign_in_codes_cannot_be_turned_on_when_nothing_can_send_them(client, make_user, app):
    """The log mailer writes codes to a file nobody signing in can read."""
    user = make_user()
    app.state.mailer = LogMailer(explicit=True)

    refused = client.patch(
        "/api/auth/preferences", json={"email_otp_enabled": True}, headers=user["headers"]
    )
    assert refused.status_code == 409
    assert "mail provider" in refused.json()["error"]["message"]

    capabilities = client.get("/api/auth/capabilities", headers=user["headers"]).json()
    assert capabilities["email_delivery"] is False

    # And the account still signs in with just its password.
    assert client.post("/api/auth/token", json={"email": user["email"], "password": user["password"]}).status_code == 200


def test_capabilities_report_a_working_mailer(client, make_user):
    user = make_user()
    capabilities = client.get("/api/auth/capabilities", headers=user["headers"]).json()
    assert capabilities["email_delivery"] is True


def test_enrolment_writes_nothing_when_the_qr_cannot_be_drawn(client, session_factory, monkeypatch):
    """A deploy that cannot draw the QR used to leave a half-made administrator behind.

    The account row was committed before the image was rendered, so the failure left a
    founder account with a secret nobody had seen and a link that answered 500. Now the
    image is rendered first and a failure writes nothing at all.
    """
    with session_factory() as session:
        _invite, token = enrolment.issue_invite(session, email="founder@example.com", role="founder")

    def explode(_url: str) -> str:
        raise RuntimeError("no image backend")

    monkeypatch.setattr(enrolment, "qr_data_uri", explode)
    with pytest.raises(RuntimeError):
        client.post(f"/admin/auth/enrol/{token}", json={"password": "a-long-admin-passphrase"})

    with session_factory() as session:
        assert session.scalars(select(AdminUser)).all() == []
        invite = session.scalars(select(AdminInvite)).one()
        assert invite.used_at is None

    # The link is untouched, so the same link works once the deploy is fixed.
    monkeypatch.undo()
    retried = client.post(f"/admin/auth/enrol/{token}", json={"password": "a-long-admin-passphrase"})
    assert retried.status_code == 200, retried.text
    assert retried.json()["qr_data_uri"].startswith("data:image/png;base64,")
