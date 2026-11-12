"""Email codes: verification, sign-in second factor, password reset.

Each rule from the policy is pinned here: six digits, five minutes, one use, five
attempts, a sixty second resend cooldown, hourly caps per address and per IP, only a
keyed digest stored, generic answers that never reveal whether an address has an
account, and a reset that ends other sessions.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.time import utcnow
from app.db.models import AdminUser, EmailCode, User
from app.main import create_app
from app.services import email_codes
from app.services.mailer import CapturingMailer, EmailMessage, MailError, ResendMailer
from tests.support import DEFAULT_PASSWORD, code_sent_to

PASSWORD = DEFAULT_PASSWORD


@pytest.fixture()
def tune(monkeypatch):
    """Override frozen settings for one test, in the modules that read them."""

    def _tune(**overrides):
        adjusted = replace(settings, **overrides)
        monkeypatch.setattr(email_codes, "settings", adjusted)
        monkeypatch.setattr("app.api.routes_auth.settings", adjusted)
        return adjusted

    return _tune


def _codes(session_factory, email: str) -> list[EmailCode]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(EmailCode).where(EmailCode.email == email).order_by(EmailCode.created_at)
            ).all()
        )


def _user_row(session_factory, email: str) -> User:
    with session_factory() as session:
        return session.scalars(select(User).where(User.email == email)).one()


# --------------------------------------------------------------- the happy path
def test_registration_sends_one_six_digit_code_and_nothing_before_it(client, mailer):
    email = "new@example.com"
    registered = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201
    assert registered.json()["email_verified"] is False

    message = mailer.last(email)
    assert message is not None
    assert message.subject == "Your ECHO verification code"
    code = mailer.code_for(email)
    assert len(code) == 6 and code.isdigit()
    assert "expires in 5 minutes" in message.text

    # Unconfirmed: signing in is refused and says why, without disclosing anything
    # about anyone else's account.
    blocked = client.post("/api/auth/token", json={"email": email, "password": PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "email_not_verified"


def test_confirming_the_code_verifies_and_signs_in(client, mailer, session_factory):
    email = "confirm@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    confirmed = client.post(
        "/api/auth/verification/confirm", json={"email": email, "code": mailer.code_for(email)}
    )
    assert confirmed.status_code == 200, confirmed.text
    token = confirmed.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email_verified"] is True
    assert _user_row(session_factory, email).email_verified is True

    # And the ordinary path works afterwards, without another code.
    signed_in = client.post("/api/auth/token", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200


def test_a_code_cannot_be_used_twice(client, mailer):
    email = "once@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    code = mailer.code_for(email)
    first = client.post("/api/auth/verification/confirm", json={"email": email, "code": code})
    assert first.status_code == 200
    second = client.post("/api/auth/verification/confirm", json={"email": email, "code": code})
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "invalid_code"


# ------------------------------------------------------------- storage and limits
def test_only_a_keyed_digest_is_stored(client, mailer, session_factory):
    email = "digest@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    code = mailer.code_for(email)
    rows = _codes(session_factory, email)
    assert len(rows) == 1
    stored = rows[0].code_hash
    # Not the code, and not a plain hash of it either: a table of a million hashes
    # would otherwise hand over every code.
    assert code not in stored
    assert stored != hashlib.sha256(code.encode()).hexdigest()
    assert stored == email_codes.digest_code(email, email_codes.VERIFY_EMAIL, code)


def test_the_same_code_hashes_differently_for_different_addresses(client, mailer):
    client.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    client.post("/api/auth/register", json={"email": "b@example.com", "password": PASSWORD})
    digest_a = email_codes.digest_code("a@example.com", email_codes.VERIFY_EMAIL, "000000")
    digest_b = email_codes.digest_code("b@example.com", email_codes.VERIFY_EMAIL, "000000")
    assert digest_a != digest_b


def test_a_code_dies_after_five_minutes(client, mailer, session_factory):
    email = "expiry@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    code = mailer.code_for(email)
    with session_factory() as session:
        row = session.scalars(select(EmailCode).where(EmailCode.email == email)).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    late = client.post("/api/auth/verification/confirm", json={"email": email, "code": code})
    assert late.status_code == 401


def test_five_wrong_guesses_kill_the_code(client, mailer, session_factory):
    email = "attempts@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    code = mailer.code_for(email)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        attempt = client.post("/api/auth/verification/confirm", json={"email": email, "code": wrong})
        assert attempt.status_code == 401
    # Even the right code is now worthless.
    dead = client.post("/api/auth/verification/confirm", json={"email": email, "code": code})
    assert dead.status_code == 401
    row = _codes(session_factory, email)[0]
    assert row.attempts == 5
    assert row.consumed_at is not None


def test_resend_waits_sixty_seconds(client, mailer):
    email = "cooldown@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert len(mailer.sent) == 1

    again = client.post("/api/auth/verification/send", json={"email": email})
    assert again.status_code == 202
    assert len(mailer.sent) == 1, "a second message inside the cooldown must not be sent"


def test_a_new_code_retires_the_old_one(client, mailer, session_factory, tune):
    tune(email_code_cooldown_seconds=0)
    email = "supersede@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    first = mailer.code_for(email)

    client.post("/api/auth/verification/send", json={"email": email})
    second = mailer.code_for(email)
    assert second != first

    old = client.post("/api/auth/verification/confirm", json={"email": email, "code": first})
    assert old.status_code == 401, "the superseded code must not work"
    good = client.post("/api/auth/verification/confirm", json={"email": email, "code": second})
    assert good.status_code == 200


def test_hourly_cap_per_address(client, mailer, tune):
    tune(email_code_cooldown_seconds=0, email_code_hourly_per_address=2)
    email = "cap@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    client.post("/api/auth/verification/send", json={"email": email})
    assert len(mailer.sent) == 2
    client.post("/api/auth/verification/send", json={"email": email})
    assert len(mailer.sent) == 2, "the third request inside the hour must be dropped"


def test_hourly_cap_per_ip(tune, session_factory):
    tune(email_code_cooldown_seconds=0, email_code_hourly_per_ip=2)
    app = create_app(session_factory=session_factory)
    app.state.mailer = mailer = CapturingMailer()
    with TestClient(app) as client:
        for index in range(4):
            client.post("/api/auth/register", json={"email": f"ip{index}@example.com", "password": PASSWORD})
    # Two addresses got their code; the rest were dropped by the per-IP cap, all from
    # the same TestClient address.
    assert len(mailer.sent) == 2


# ------------------------------------------------------------------ no enumeration
def test_asking_for_a_code_answers_the_same_for_known_and_unknown_addresses(client, mailer, tune):
    # With a provider configured there is no development echo, which is the shape a
    # real deployment runs: the two answers must then be byte-identical.
    tune(email_provider="resend", resend_api_key="re_test", email_verification_required=True)
    client.post("/api/auth/register", json={"email": "known@example.com", "password": PASSWORD})
    for path in ("/api/auth/verification/send", "/api/auth/password/forgot"):
        known = client.post(path, json={"email": "known@example.com"})
        unknown = client.post(path, json={"email": "nobody-at-all@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json(), f"{path} leaks whether the address exists"
    # And nothing was sent to the address that has no account.
    assert mailer.last("nobody-at-all@example.com") is None


def test_development_echo_is_off_as_soon_as_a_provider_exists(tune):
    # Honest about the one place existence leaks: local development, where the code is
    # handed back in the response because there is no mailbox. It cannot happen in
    # production, because production refuses to start without a provider.
    assert settings.email_dev_echo is True
    assert tune(email_provider="resend", resend_api_key="re_test").email_dev_echo is False
    assert tune(env="production", email_provider=None, resend_api_key=None).email_dev_echo is False


def test_production_refuses_to_start_without_a_mail_provider(monkeypatch):
    from app.core.config import load_settings

    monkeypatch.setenv("ECHO_ENV", "production")
    monkeypatch.setenv("ECHO_DATA_KEY", settings.email_code_pepper or "a" * 32)
    monkeypatch.setenv("ECHO_USER_JWT_SECRET", "prod-user-secret-0123456789")
    monkeypatch.setenv("ECHO_ADMIN_JWT_SECRET", "prod-admin-secret-0123456789")
    monkeypatch.delenv("ECHO_RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ECHO_EMAIL_PROVIDER", raising=False)
    monkeypatch.setenv("ECHO_EMAIL_VERIFICATION_REQUIRED", "true")
    with pytest.raises(RuntimeError) as caught:
        load_settings()
    assert "ECHO_RESEND_API_KEY" in str(caught.value)


# ------------------------------------------------------------- sign-in codes (MFA)
def test_sign_in_code_is_optional_and_can_be_turned_on(client, mailer, session_factory):
    email = "otp@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post(
        "/api/auth/verification/confirm", json={"email": email, "code": mailer.code_for(email)}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    enabled = client.patch("/api/auth/preferences", json={"email_otp_enabled": True}, headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["email_otp_enabled"] is True

    challenge = client.post("/api/auth/token", json={"email": email, "password": PASSWORD})
    assert challenge.status_code == 401
    assert challenge.json()["error"]["code"] == "email_code_required"
    login_code = mailer.code_for(email)
    assert mailer.last(email).subject == "Your ECHO sign-in code"

    wrong = client.post(
        "/api/auth/token/code", json={"email": email, "password": PASSWORD, "code": "000000" if login_code != "000000" else "111111"}
    )
    assert wrong.status_code == 401

    finished = client.post(
        "/api/auth/token/code", json={"email": email, "password": PASSWORD, "code": login_code}
    )
    assert finished.status_code == 200, finished.text


def test_a_verification_code_cannot_stand_in_for_a_sign_in_code(client, mailer, tune):
    tune(email_code_cooldown_seconds=0)
    email = "purpose@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    verify_code = mailer.code_for(email)
    token = client.post(
        "/api/auth/verification/confirm", json={"email": email, "code": verify_code}
    ).json()["access_token"]
    client.patch(
        "/api/auth/preferences", json={"email_otp_enabled": True}, headers={"Authorization": f"Bearer {token}"}
    )
    client.post("/api/auth/token", json={"email": email, "password": PASSWORD})
    # A stale verification code must not satisfy the sign-in step.
    reused = client.post(
        "/api/auth/token/code", json={"email": email, "password": PASSWORD, "code": verify_code}
    )
    assert reused.status_code == 401


def test_sign_in_codes_need_a_verified_address(client, mailer, session_factory):
    email = "unverified-otp@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    with session_factory() as session:
        user = session.scalars(select(User).where(User.email == email)).one()
        # A token minted before verification is enough to reach the endpoint.
        from app.core.security import create_access_token

        token = create_access_token(user.id)
    refused = client.patch(
        "/api/auth/preferences",
        json={"email_otp_enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert refused.status_code == 403


# ------------------------------------------------------------------ password reset
def test_password_reset_code_changes_the_password_and_ends_older_sessions(client, mailer):
    email = "reset@example.com"
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    old_token = client.post(
        "/api/auth/verification/confirm", json={"email": email, "code": mailer.code_for(email)}
    ).json()["access_token"]
    old_headers = {"Authorization": f"Bearer {old_token}"}
    assert client.get("/api/auth/me", headers=old_headers).status_code == 200

    client.post("/api/auth/password/forgot", json={"email": email})
    code = mailer.code_for(email)
    reset = client.post(
        "/api/auth/password/reset", json={"email": email, "code": code, "password": "a-brand-new-passphrase"}
    )
    assert reset.status_code == 200, reset.text

    # The new password works, the old one does not, and the old token is dead.
    assert client.post("/api/auth/token", json={"email": email, "password": "a-brand-new-passphrase"}).status_code == 200
    assert client.post("/api/auth/token", json={"email": email, "password": PASSWORD}).status_code == 401
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401


def test_a_reset_code_does_not_touch_administrators(client, make_admin, mailer, session_factory):
    admin = make_admin(email="founder@example.com")
    client.post("/api/auth/password/forgot", json={"email": "founder@example.com"})
    # Administrators are not `users`, so no reset code is minted for them at all.
    assert mailer.last("founder@example.com") is None
    with session_factory() as session:
        assert session.scalars(select(AdminUser).where(AdminUser.email == "founder@example.com")).one().id == admin["id"]
    # A user code cannot open the admin console, which needs password *and* TOTP.
    refused = client.post(
        "/admin/auth/token", json={"email": "founder@example.com", "password": admin["password"], "totp_code": "000000"}
    )
    assert refused.status_code in (401, 422)


# ------------------------------------------------------------------- delivery wire
class _FakeResend:
    """A real HTTP server on a real socket, so the wire format is what is asserted."""

    def __init__(self, status: int = 200) -> None:
        self.requests: list[dict] = []
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "json": body})
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"id": "msg_1"}).encode())

            def log_message(self, *args) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _FakeResend:
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def test_resend_mailer_sends_the_documented_request():
    with _FakeResend() as fake:
        mailer = ResendMailer("re_test_key", sender="ECHO <codes@echo.app>", base_url=fake.base_url, timeout=5)
        mailer.send(
            EmailMessage(to="someone@example.com", subject="Your ECHO code", text="123456", html="<p>123456</p>")
        )
    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request["path"] == "/emails"
    assert request["headers"]["Authorization"] == "Bearer re_test_key"
    assert request["json"]["from"] == "ECHO <codes@echo.app>"
    assert request["json"]["to"] == ["someone@example.com"]
    assert request["json"]["subject"] == "Your ECHO code"
    assert "123456" in request["json"]["text"]


def test_resend_refusal_is_an_error_not_a_silent_noop():
    with _FakeResend(status=422) as fake:
        mailer = ResendMailer("re_test_key", sender="ECHO <codes@echo.app>", base_url=fake.base_url, timeout=5)
        with pytest.raises(MailError):
            mailer.send(EmailMessage(to="x@example.com", subject="s", text="t"))


def test_a_failed_delivery_burns_the_code_instead_of_blocking_a_retry(tune, session_factory):
    tune(email_code_cooldown_seconds=60)

    class Refusing:
        name = "refusing"

        def send(self, message):  # noqa: ANN001
            raise MailError("provider down")

    app = create_app(session_factory=session_factory)
    app.state.mailer = Refusing()
    with TestClient(app) as client:
        registered = client.post("/api/auth/register", json={"email": "down@example.com", "password": PASSWORD})
        assert registered.status_code == 201, "registration must not fail because mail is down"
        attempt = client.post("/api/auth/verification/send", json={"email": "down@example.com"})
        assert attempt.status_code == 202
    rows = _codes(session_factory, "down@example.com")
    assert rows, "the code was attempted"
    assert all(row.consumed_at is not None for row in rows), "undelivered codes must not stay live"
