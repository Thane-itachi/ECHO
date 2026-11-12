"""One error envelope for the whole API: {"error": {"code", "message"}}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("echo")


class EchoError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(EchoError):
    status_code = 404
    code = "not_found"


class Conflict(EchoError):
    status_code = 409
    code = "conflict"


class Unauthorized(EchoError):
    status_code = 401
    code = "unauthorized"


class Forbidden(EchoError):
    status_code = 403
    code = "forbidden"


class InvalidRequest(EchoError):
    status_code = 422
    code = "invalid_request"


class PayloadTooLarge(EchoError):
    status_code = 413
    code = "payload_too_large"


def _body(code: str, message: str, details=None) -> dict:
    payload: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EchoError)
    async def _echo_error(_: Request, exc: EchoError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            _body("validation_error", "request validation failed", jsonable_encoder(exc.errors())),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body("internal_error", "internal server error"), status_code=500)
