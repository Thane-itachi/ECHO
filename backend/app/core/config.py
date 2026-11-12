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
        if not settings.storage_dir:
            problems.append("ECHO_STORAGE_DIR must be set (documents are stored encrypted on disk)")
        if problems:
            raise RuntimeError("refusing to start: " + "; ".join(problems))
    return settings


settings = load_settings()
