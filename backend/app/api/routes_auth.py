from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.config import settings
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.core.security import DUMMY_HASH, USER_AUDIENCE, create_access_token, verify_password
from app.db.models import User
from app.repositories.system import UserRepository
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    users = UserRepository(db)
    if users.by_email(payload.email) is not None:
        raise Conflict("an account with this email already exists")
    user = users.create(email=payload.email, password=payload.password)
    db.commit()
    return user


@router.post("/token", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    users = UserRepository(db)
    user = users.by_email(payload.email)
    if user is None:
        # Same work, same message: no account enumeration, no timing oracle.
        verify_password(payload.password, DUMMY_HASH)
        raise Unauthorized("invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        raise Unauthorized("invalid email or password")
    if not user.is_active:
        raise Forbidden("this account has been disabled")
    token = create_access_token(user.id, audience=USER_AUDIENCE)
    return TokenResponse(access_token=token, expires_in=settings.user_token_ttl_seconds)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)) -> User:
    return user
