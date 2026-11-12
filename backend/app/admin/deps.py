"""Admin-side dependencies.

Deliberately duplicated rather than shared with `app.api.deps`: the admin gate has
to be provable in isolation, so this module imports only core primitives and the
AdminUser model. Nothing here can obtain a User session or a decrypting repository.
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Unauthorized
from app.core.security import ADMIN_AUDIENCE, TokenError, decode_access_token
from app.db.models import AdminUser

admin_bearer = HTTPBearer(auto_error=False, description="Admin bearer token (MFA verified at login)")


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
    db: Session = Depends(get_db),
) -> AdminUser:
    if credentials is None or not credentials.credentials:
        raise Unauthorized("missing admin token")
    try:
        payload = decode_access_token(credentials.credentials, audience=ADMIN_AUDIENCE)
    except TokenError as exc:
        raise Unauthorized("invalid or expired admin token") from exc
    admin = db.get(AdminUser, payload["sub"])
    if admin is None or not admin.is_active:
        raise Unauthorized("invalid or expired admin token")
    return admin
