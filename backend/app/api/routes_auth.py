"""User authentication.

Ordinary users prove an address with a six-digit emailed code, and may opt into a code
at every sign-in. Administrators are entirely separate: they live in `admin_users`,
never touch these routes, and always need their authenticator app (see app/admin).

Two things this file is careful about:

* Every "we sent you a code" answer is identical whether or not the address has an
  account. The only difference is an email nobody else can read.
* A password reset bumps `credentials_changed_at`, and `current_user` rejects tokens
  minted before it, so a reset actually ends other sessions.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.config import settings
from app.core.errors import Conflict, EchoError, Forbidden, Unauthorized
from app.core.security import (
    DUMMY_HASH,
    USER_AUDIENCE,
    create_access_token,
    hash_password,
    password_version,
    verify_password,
)
from app.core.time import utcnow
from app.db.models import User
from app.repositories.system import UserRepository
from app.schemas import (
    AuthPreferences,
    CodeSubmission,
    EmailCodeRequest,
    LoginRequest,
    LoginWithCodeRequest,
    PasswordResetRequest,
    RegisterRequest,
    ReminderEmailPreference,
    StatusResponse,
    TokenResponse,
    UserRead,
)
from app.services import email_codes
from app.services.mailer import Mailer

logger = logging.getLogger("echo.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

#: One answer for "send me a code", whatever the truth is.
_CODE_SENT = "if that address can receive mail, a code is on its way"


class EmailCodeRequired(EchoError):
    """Correct password, but this account finishes signing in with an emailed code."""

    status_code = 401
    code = "email_code_required"


class EmailVerificationRequired(EchoError):
    """Correct password, but the address was never confirmed."""

    status_code = 403
    code = "email_not_verified"


class InvalidCode(EchoError):
    status_code = 401
    code = "invalid_code"


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer


def _client_ip(request: Request) -> str | None:
    # Deliberately not X-Forwarded-For: a header a client controls is not an identity.
    return request.client.host if request.client else None


def _issue(session: Session, request: Request, *, email: str, purpose: str, user: User | None) -> str | None:
    """Best-effort code delivery. Never raises for cooldown or provider trouble."""
    code: str | None = None
    try:
        code = email_codes.issue(
            session,
            email=email,
            purpose=purpose,
            mailer=get_mailer(request),
            user=user,
            request_ip=_client_ip(request),
        )
    except email_codes.CodeCooldown:
        logger.info("code request for %s (%s) inside the cooldown; nothing sent", email, purpose)
    except email_codes.CodeRateLimited:
        logger.warning("code request for %s (%s) hit an hourly cap; nothing sent", email, purpose)
    except email_codes.CodeDeliveryFailed:
        logger.error("code for %s (%s) could not be delivered", email, purpose)
    # Commit outside the try: a code that was created has to reach the database, and a
    # retirement of older codes must land with it.
    session.commit()
    return code


def _dev_echo(code: str | None) -> str | None:
    """Only in development with no provider: hand the code back over the API."""
    return code if settings.email_dev_echo else None


def _token_for(user: User) -> TokenResponse:
    token = create_access_token(
        user.id, audience=USER_AUDIENCE, extra={"pv": password_version(user.password_hash)}
    )
    return TokenResponse(access_token=token, expires_in=settings.user_token_ttl_seconds)


def _check_password(session: Session, email: str, password: str) -> User:
    user = UserRepository(session).by_email(email)
    if user is None:
        # Same work, same message: no account enumeration, no timing oracle.
        verify_password(password, DUMMY_HASH)
        raise Unauthorized("invalid email or password")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("invalid email or password")
    if not user.is_active:
        raise Forbidden("this account has been disabled")
    return user


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> User:
    users = UserRepository(db)
    if users.by_email(payload.email) is not None:
        raise Conflict("an account with this email already exists")
    user = users.create(email=payload.email, password=payload.password)
    code: str | None = None
    if settings.email_verification_required:
        user.email_verified = False
        db.commit()
        code = _issue(db, request, email=user.email, purpose=email_codes.VERIFY_EMAIL, user=user)
    else:
        user.email_verified = True
    db.commit()
    db.refresh(user)
    response = UserRead.model_validate(user)
    if code and settings.email_dev_echo:
        # Walk the flow locally without a mailbox. Absent in production, always.
        response.dev_code = code
    return response


@router.post("/verification/send", response_model=StatusResponse, status_code=202)
def send_verification(payload: EmailCodeRequest, request: Request, db: Session = Depends(get_db)) -> StatusResponse:
    user = UserRepository(db).by_email(payload.email)
    code = None
    if user is not None and user.is_active and not user.email_verified:
        code = _issue(db, request, email=user.email, purpose=email_codes.VERIFY_EMAIL, user=user)
    return StatusResponse(status="sent", dev_code=_dev_echo(code))


@router.post("/verification/confirm", response_model=TokenResponse)
def confirm_verification(payload: CodeSubmission, db: Session = Depends(get_db)) -> TokenResponse:
    user = UserRepository(db).by_email(payload.email)
    try:
        email_codes.consume(db, email=payload.email, purpose=email_codes.VERIFY_EMAIL, code=payload.code)
    except email_codes.CodeRejected as exc:
        db.commit()
        raise InvalidCode(str(exc)) from exc
    if user is None:
        # A code existed for a deleted account: the code is spent either way.
        db.commit()
        raise Unauthorized("invalid email or password")
    if not user.is_active:
        db.commit()
        raise Forbidden("this account has been disabled")
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/token", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = _check_password(db, payload.email, payload.password)

    if settings.email_verification_required and not user.email_verified:
        _issue(db, request, email=user.email, purpose=email_codes.VERIFY_EMAIL, user=user)
        raise EmailVerificationRequired("confirm your email address before signing in")

    if user.email_otp_enabled:
        code = _issue(db, request, email=user.email, purpose=email_codes.LOGIN_OTP, user=user)
        message = "this account finishes signing in with a code by email"
        if code is None:
            # Inside the resend cooldown, so the earlier code is still the live one.
            message = "a sign-in code was emailed moments ago and is still valid"
        raise EmailCodeRequired(message, details={"dev_code": _dev_echo(code)})

    return _token_for(user)


@router.post("/token/code", response_model=TokenResponse)
def login_with_code(payload: LoginWithCodeRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    """Second step for accounts that turned on an emailed sign-in code."""
    user = _check_password(db, payload.email, payload.password)
    if not user.email_otp_enabled:
        raise Unauthorized("this account does not use a code by email")
    if settings.email_verification_required and not user.email_verified:
        raise EmailVerificationRequired("confirm your email address before signing in")
    try:
        email_codes.consume(db, email=user.email, purpose=email_codes.LOGIN_OTP, code=payload.code)
    except email_codes.CodeRejected as exc:
        db.commit()
        raise InvalidCode(str(exc)) from exc
    db.commit()
    return _token_for(user)


@router.post("/password/forgot", response_model=StatusResponse, status_code=202)
def forgot_password(payload: EmailCodeRequest, request: Request, db: Session = Depends(get_db)) -> StatusResponse:
    user = UserRepository(db).by_email(payload.email)
    code = None
    if user is not None and user.is_active:
        code = _issue(db, request, email=user.email, purpose=email_codes.PASSWORD_RESET, user=user)
    return StatusResponse(status="sent", dev_code=_dev_echo(code))


@router.post("/password/reset", response_model=StatusResponse)
def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)) -> StatusResponse:
    user = UserRepository(db).by_email(payload.email)
    try:
        email_codes.consume(db, email=payload.email, purpose=email_codes.PASSWORD_RESET, code=payload.code)
    except email_codes.CodeRejected as exc:
        db.commit()
        raise InvalidCode(str(exc)) from exc
    if user is None or not user.is_active:
        db.commit()
        raise Unauthorized("invalid email or password")
    user.password_hash = hash_password(payload.password)
    # Proving the address and choosing a new password also confirms the address.
    user.email_verified = True
    user.credentials_changed_at = utcnow()
    db.commit()
    return StatusResponse(status="password_reset")


@router.patch("/preferences", response_model=UserRead)
def update_preferences(
    payload: AuthPreferences, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> User:
    if payload.email_otp_enabled and not user.email_verified:
        raise Forbidden("confirm your email address before turning on codes at sign-in")
    user.email_otp_enabled = payload.email_otp_enabled
    db.commit()
    db.refresh(user)
    return user


@router.patch("/reminder-email", response_model=UserRead)
def set_reminder_email(
    payload: ReminderEmailPreference, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> User:
    """The switch behind reminder email, separate from `/preferences`: signing in with
    a code and being reminded about a promise are unrelated choices, and the code one
    has a verification precondition this one does not need."""
    user.reminder_email_enabled = payload.enabled
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)) -> User:
    return user
