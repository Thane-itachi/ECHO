"""Runtime configuration.

Everything comes from the environment. No secrets in code, no defaults that are
safe to ship to production: `load_settings()` refuses to start in production with
dev secrets or without a data key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    return int(raw)


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    if raw is None:
        return default
    return float(raw)


def _get_bool(name: str, default: bool = False) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    user_jwt_secret: str
    admin_jwt_secret: str
    user_token_ttl_seconds: int
    admin_token_ttl_seconds: int
    data_key: str | None
    #: Keys that may still decrypt but never encrypt: the rotation window.
    data_key_previous: tuple[str, ...]
    password_iterations: int
    cors_origins: tuple[str, ...]
    sql_echo: bool
    storage_dir: str
    max_upload_bytes: int
    #: Optional model provider. `None` means "answer extractive, extract with rules",
    #: which is a supported configuration, not a degraded one.
    llm_provider: str | None
    openai_api_key: str | None
    openai_base_url: str
    llm_model: str
    llm_timeout_seconds: float
    llm_extraction: bool
    #: Where sign-in and verification codes are delivered. Resend is the only
    #: provider wired today; with no key the codes are logged instead of sent, which
    #: is fine for local work and refused in production.
    email_provider: str | None
    resend_api_key: str | None
    resend_base_url: str
    email_from: str
    email_timeout_seconds: float
    email_verification_required: bool
    email_code_ttl_seconds: int
    email_code_max_attempts: int
    email_code_cooldown_seconds: int
    email_code_hourly_per_address: int
    email_code_hourly_per_ip: int
    #: Pepper for the stored code digests. A bare SHA of a six-digit code is not a
    #: hash, it is a lookup table, so the digest is keyed.
    email_code_pepper: str | None
    #: Web Push (notifications to the user's phone or desktop). The VAPID keypair
    #: identifies this server to the push service; the public half is handed to the
    #: browser, the private half never leaves the process. With no keypair the push
    #: endpoints answer "not configured" instead of failing at send time.
    vapid_public_key: str | None
    vapid_private_key: str | None
    vapid_subject: str
    push_timeout_seconds: float

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def admin_mfa_required(self) -> bool:
        """Administrator MFA is not optional, in any environment.

        It used to be a per-row flag that a CLI switch could turn off while the token
        still carried `mfa=true`. There is no switch now: the only way to obtain an
        admin token is to pass TOTP verification.
        """
        return True

    @property
    def llm_enabled(self) -> bool:
        """True only when a provider is named *and* it has a key.

        A key with no provider named is taken to mean OpenAI (pasting a key is the
        intent), and naming any other provider is refused at startup rather than
        silently falling back. Either way the startup log says which path is live, so
        "did the model actually turn on?" is answerable without guessing.
        """
        return self.llm_provider == "openai" and bool(self.openai_api_key)

    @property
    def email_enabled(self) -> bool:
        """True only when a provider is named *and* it has a key."""
        return self.email_provider == "resend" and bool(self.resend_api_key)

    @property
    def push_enabled(self) -> bool:
        """A keypair, both halves, or nothing: half a keypair cannot sign anything."""
        return bool(self.vapid_public_key and self.vapid_private_key)

    @property
    def email_dev_echo(self) -> bool:
        """Development convenience: hand the code back in the API response.

        Never true in production, and never true once a real provider is configured:
        otherwise the API would be the delivery channel and the mailbox decoration.
        """
        return not self.is_production and not self.email_enabled

    @property
    def is_test(self) -> bool:
        return self.env.lower() in {"test", "testing"}


def load_settings() -> Settings:
    settings = Settings(
        env=(_get("ECHO_ENV", "development") or "development").lower(),
        database_url=_get("ECHO_DATABASE_URL", "sqlite+pysqlite:///./echo.db") or "",
        user_jwt_secret=_get("ECHO_USER_JWT_SECRET", "dev-user-jwt-secret-change-me") or "",
        admin_jwt_secret=_get("ECHO_ADMIN_JWT_SECRET", "dev-admin-jwt-secret-change-me") or "",
        user_token_ttl_seconds=_get_int("ECHO_USER_TOKEN_TTL", 60 * 60 * 12),
        admin_token_ttl_seconds=_get_int("ECHO_ADMIN_TOKEN_TTL", 60 * 15),
        data_key=_get("ECHO_DATA_KEY"),
        data_key_previous=tuple(
            key.strip() for key in (_get("ECHO_DATA_KEY_PREVIOUS", "") or "").split(",") if key.strip()
        ),
        password_iterations=_get_int("ECHO_PASSWORD_ITERATIONS", 120_000),
        cors_origins=tuple(
            origin.strip()
            for origin in (_get("ECHO_CORS_ORIGINS", "http://localhost:5173") or "").split(",")
            if origin.strip()
        ),
        sql_echo=_get_bool("ECHO_SQL_ECHO", False),
        storage_dir=_get("ECHO_STORAGE_DIR", "./storage") or "./storage",
        max_upload_bytes=_get_int("ECHO_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        llm_provider=(_get("ECHO_LLM_PROVIDER") or ("openai" if _get("ECHO_OPENAI_API_KEY") else None)),
        openai_api_key=_get("ECHO_OPENAI_API_KEY"),
        # Point this at http://localhost:11434/v1 for a local Ollama: same wire protocol.
        openai_base_url=_get("ECHO_OPENAI_BASE_URL", "https://api.openai.com/v1") or "",
        llm_model=_get("ECHO_LLM_MODEL", "gpt-4o-mini") or "",
        llm_timeout_seconds=_get_float("ECHO_LLM_TIMEOUT", 20.0),
        llm_extraction=_get_bool("ECHO_LLM_EXTRACTION", True),
        email_provider=_get("ECHO_EMAIL_PROVIDER") or ("resend" if _get("ECHO_RESEND_API_KEY") else None),
        resend_api_key=_get("ECHO_RESEND_API_KEY"),
        resend_base_url=_get("ECHO_RESEND_BASE_URL", "https://api.resend.com") or "",
        # Resend only lets you send from a domain you have verified, or their test sender.
        email_from=_get("ECHO_EMAIL_FROM", "ECHO <onboarding@resend.dev>") or "",
        email_timeout_seconds=_get_float("ECHO_EMAIL_TIMEOUT", 10.0),
        email_verification_required=_get_bool("ECHO_EMAIL_VERIFICATION_REQUIRED", True),
        email_code_ttl_seconds=_get_int("ECHO_EMAIL_CODE_TTL", 300),
        email_code_max_attempts=_get_int("ECHO_EMAIL_CODE_MAX_ATTEMPTS", 5),
        email_code_cooldown_seconds=_get_int("ECHO_EMAIL_CODE_COOLDOWN", 60),
        email_code_hourly_per_address=_get_int("ECHO_EMAIL_CODE_HOURLY_PER_ADDRESS", 5),
        email_code_hourly_per_ip=_get_int("ECHO_EMAIL_CODE_HOURLY_PER_IP", 20),
        email_code_pepper=_get("ECHO_EMAIL_CODE_PEPPER"),
        vapid_public_key=_get("ECHO_VAPID_PUBLIC_KEY"),
        # PEM on one line with literal \n is the shape that survives an env file.
        vapid_private_key=(_get("ECHO_VAPID_PRIVATE_KEY") or "").replace("\\n", "\n") or None,
        vapid_subject=_get("ECHO_VAPID_SUBJECT", "mailto:push@example.com") or "mailto:push@example.com",
        push_timeout_seconds=_get_float("ECHO_PUSH_TIMEOUT", 10.0),
    )
    if settings.is_production:
        problems = []
        if not settings.data_key:
            problems.append("ECHO_DATA_KEY is required (memory content is encrypted at rest)")
        if "change-me" in settings.user_jwt_secret or "change-me" in settings.admin_jwt_secret:
            problems.append("ECHO_USER_JWT_SECRET and ECHO_ADMIN_JWT_SECRET must be set")
        if settings.user_jwt_secret == settings.admin_jwt_secret:
            problems.append("user and admin signing keys must differ")
        if settings.llm_provider and settings.llm_provider != "openai":
            problems.append("ECHO_LLM_PROVIDER must be 'openai' (openai-compatible servers go via ECHO_OPENAI_BASE_URL)")
        if settings.llm_provider and not settings.openai_api_key:
            problems.append("ECHO_OPENAI_API_KEY is required when ECHO_LLM_PROVIDER is set")
        if settings.data_key and settings.data_key in settings.data_key_previous:
            problems.append("ECHO_DATA_KEY_PREVIOUS must not repeat the current ECHO_DATA_KEY")
        if settings.email_provider and not settings.resend_api_key:
            problems.append("ECHO_RESEND_API_KEY is required when ECHO_EMAIL_PROVIDER is set")
        if settings.email_verification_required and not settings.resend_api_key:
            problems.append(
                "ECHO_RESEND_API_KEY is required to verify addresses "
                "(or set ECHO_EMAIL_VERIFICATION_REQUIRED=false to skip verification)"
            )
        if settings.email_code_pepper and len(settings.email_code_pepper) < 16:
            problems.append("ECHO_EMAIL_CODE_PEPPER must be at least 16 characters")
        if not settings.storage_dir:
            problems.append("ECHO_STORAGE_DIR must be set (documents are stored encrypted on disk)")
        if problems:
            raise RuntimeError("refusing to start: " + "; ".join(problems))
    return settings


settings = load_settings()
