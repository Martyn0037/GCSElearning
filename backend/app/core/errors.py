# backend/app/core/errors.py
"""Application errors and the single error-response shape.

Every error leaves the API as::

    {"error": {"code": "...", "message": "...", "traceId": "..."}}
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import current_trace_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An expected error that maps to a specific HTTP status and code.

    Attributes:
        status_code: HTTP status to return.
        code: Stable machine-readable code, e.g. ``RESOURCE_NOT_FOUND``.
        message: Human-readable message safe to show the user.
        headers: Optional extra response headers (e.g. ``Retry-After``).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


class NotFoundError(AppError):
    """The resource does not exist, or the caller may not know it exists."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(HTTPStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", message)


class AuthenticationError(AppError):
    """The caller is not authenticated, or their credentials are invalid."""

    def __init__(self, message: str = "Authentication required", code: str = "UNAUTHENTICATED"):
        super().__init__(HTTPStatus.UNAUTHORIZED, code, message)


class PermissionDeniedError(AppError):
    """The caller is authenticated but may not perform this action."""

    def __init__(self, message: str = "You do not have permission to do that") -> None:
        super().__init__(HTTPStatus.FORBIDDEN, "FORBIDDEN", message)


class RateLimitedError(AppError):
    """Too many requests in the current window."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            HTTPStatus.TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            "Too many requests. Please wait and try again.",
            headers={"Retry-After": str(max(1, retry_after_seconds))},
        )


_HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
}


def error_body(code: str, message: str) -> dict[str, dict[str, str | None]]:
    """Build the standard error body for the current request."""
    return {"error": {"code": code, "message": message, "traceId": current_trace_id()}}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered only for AppError
    return JSONResponse(
        error_body(exc.code, exc.message), status_code=exc.status_code, headers=exc.headers
    )


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    message = HTTPStatus(exc.status_code).phrase
    return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Name the offending fields but never echo submitted values back.
    fields = sorted({".".join(str(p) for p in err["loc"][1:]) or "body" for err in exc.errors()})
    message = "Invalid request: check " + ", ".join(fields)
    return JSONResponse(error_body("VALIDATION_ERROR", message), status_code=422)


async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", exc_info=exc)
    return JSONResponse(
        error_body("INTERNAL_ERROR", "Something went wrong. Please try again."), status_code=500
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install handlers so every error uses the standard shape."""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
