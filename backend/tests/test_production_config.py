"""The rules a production deploy has to satisfy, and the ways it is allowed to run.

A deploy is where a missing key stops being a preference and becomes an outage, so the
settings loader is strict on purpose. These tests pin both halves: what it refuses, and
the two explicit ways to run a production deploy without a mail provider or without a
durable disk, because both of those are real situations and silence is worse than a
documented compromise.
"""
from __future__ import annotations

import pytest

from app.core.config import load_settings

BASE = {
    "ECHO_ENV": "production",
    "ECHO_DATA_KEY": "dGVzdC1kYXRhLWtleS0wMTIzNDU2Nzg5YWJjZGVm",
    "ECHO_USER_JWT_SECRET": "user-secret-0123456789abcdefghij",
    "ECHO_ADMIN_JWT_SECRET": "admin-secret-0123456789abcdefgh",
    "ECHO_STORAGE_BACKEND": "vercel-blob",
    "BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_token",
    "ECHO_MAILER": "log",
    "ECHO_EMAIL_VERIFICATION_REQUIRED": "false",
}


def env(**overrides) -> dict[str, str]:
    """A complete production environment, with one thing changed."""
    values = dict(BASE)
    for key, value in overrides.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    return values


@pytest.fixture()
def configure(monkeypatch):
    def apply(**overrides):
        for name in {*BASE, *overrides, "VERCEL", "ECHO_ALLOW_EPHEMERAL_STORAGE", "ECHO_RESEND_API_KEY"}:
            monkeypatch.delenv(name, raising=False)
        for key, value in env(**overrides).items():
            monkeypatch.setenv(key, value)
        return load_settings()

    return apply


def test_a_complete_environment_loads(configure):
    settings = configure()
    assert settings.is_production
    assert settings.storage_backend == "vercel-blob"


def test_a_deploy_without_a_data_key_is_refused(configure):
    with pytest.raises(RuntimeError) as failure:
        configure(ECHO_DATA_KEY=None)
    assert "ECHO_DATA_KEY" in str(failure.value)


def test_the_same_signing_key_for_users_and_admins_is_refused(configure):
    with pytest.raises(RuntimeError) as failure:
        configure(ECHO_ADMIN_JWT_SECRET="user-secret-0123456789abcdefghij")
    assert "must differ" in str(failure.value)


def test_documents_without_durable_storage_are_refused_on_vercel(configure):
    """The scratch disk is not a store: saying so at boot beats losing the bytes later."""
    with pytest.raises(RuntimeError) as failure:
        configure(ECHO_STORAGE_BACKEND="local", VERCEL="1")
    assert "vercel-blob" in str(failure.value)


def test_ephemeral_storage_can_be_accepted_on_purpose(configure):
    settings = configure(ECHO_STORAGE_BACKEND="local", VERCEL="1", ECHO_ALLOW_EPHEMERAL_STORAGE="1")
    assert settings.storage_backend == "local"


def test_blob_storage_demands_its_token(configure):
    with pytest.raises(RuntimeError) as failure:
        configure(BLOB_READ_WRITE_TOKEN=None)
    assert "BLOB_READ_WRITE_TOKEN" in str(failure.value)


def test_no_mail_provider_at_all_is_refused(configure):
    with pytest.raises(RuntimeError) as failure:
        configure(ECHO_MAILER=None)
    assert "ECHO_MAILER=log" in str(failure.value)


def test_the_logging_mailer_cannot_be_used_while_verifying_addresses(configure):
    """A code nobody receives is a sign-up that cannot finish."""
    with pytest.raises(RuntimeError) as failure:
        configure(ECHO_MAILER="log", ECHO_EMAIL_VERIFICATION_REQUIRED="true")
    assert "verification" in str(failure.value).lower()


def test_a_resend_key_makes_the_logging_mailer_unnecessary(configure):
    settings = configure(
        ECHO_MAILER=None, ECHO_RESEND_API_KEY="re_test", ECHO_EMAIL_VERIFICATION_REQUIRED="true"
    )
    assert settings.email_enabled is True


def test_the_logging_mailer_is_an_explicit_choice_in_production(configure, monkeypatch):
    import app.services.mailer as mailer_module

    settings = configure()
    monkeypatch.setattr(mailer_module, "settings", settings)
    mailer = mailer_module.build_mailer()
    assert mailer.name == "log"
    assert mailer.explicit is True
    assert "written to the log" in mailer_module.describe(mailer)


def test_a_functional_deploy_keeps_no_pooled_connections(configure):
    """A frozen function with a pooled connection is a connection nobody closes."""
    assert configure(VERCEL="1").db_pool == "null"
    assert configure().db_pool == "default"


def test_a_managed_database_url_gets_the_installed_driver(configure):
    """Neon hands you `postgresql://`; ECHO installs psycopg 3, not psycopg2."""
    settings = configure(
        ECHO_DATABASE_URL="postgresql://user:pass@ep-x-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
    )
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in settings.database_url


def test_an_explicit_driver_is_left_alone(configure):
    url = "postgresql+psycopg://user:pass@host/db"
    assert configure(ECHO_DATABASE_URL=url).database_url == url
