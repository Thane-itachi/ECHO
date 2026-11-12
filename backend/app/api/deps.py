"""Shared FastAPI dependencies.

`get_db` reads the session factory off `app.state`, which is how tests swap in an
isolated database without monkeypatching module globals.
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import ContentCipher, NullCipher
from app.core.errors import Unauthorized
from app.core.security import USER_AUDIENCE, TokenError, decode_access_token
from app.db.models import User

bearer = HTTPBearer(auto_error=False, description="Bearer access token")


def get_db(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_cipher(request: Request) -> ContentCipher | NullCipher:
    return request.app.state.cipher


def get_llm(request: Request):
    """The configured model provider, or None. Routes never construct one themselves."""
    return getattr(request.app.state, "llm", None)


def get_storage_dir(request: Request) -> str:
    """Where encrypted documents live. Overridable per app instance (tests)."""
    return getattr(request.app.state, "storage_dir", settings.storage_dir)


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise Unauthorized("missing bearer token")
    return credentials.credentials


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = _token(credentials)
    try:
        payload = decode_access_token(token, audience=USER_AUDIENCE)
    except TokenError as exc:
        raise Unauthorized("invalid or expired token") from exc
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise Unauthorized("invalid or expired token")
    return user
