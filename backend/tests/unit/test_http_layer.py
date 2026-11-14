# backend/tests/unit/test_http_layer.py
"""Unit tests for error handling, middleware, CSRF, roles and rate-limit windows.

Uses a tiny app with test-only routes, so no database is needed.

Covers:
- AppError / 404 / 405 / validation / unhandled errors -> standard shape with traceId
- traceId in body equals X-Trace-Id header; valid incoming IDs honoured, invalid replaced
- validation errors never echo submitted values
- security headers on every response, incl. errors
- CORS: allowed origin echoed, unknown origin not
- require_csrf: safe methods pass; mismatched/missing header -> 403
- require_roles: allowed role passes, other role -> 403
- rate-limit windows align to the epoch
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth.dependencies import current_user, require_csrf, require_roles
from app.auth.rate_limit import window_start
from app.core.clock import SystemClock, get_clock
from app.core.errors import NotFoundError, register_error_handlers
from app.core.middleware import (
    SECURITY_HEADERS,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.models.user import Role, User


class _Body(BaseModel):
    secret_value: int


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=["https://ok.test"], allow_credentials=True)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("Nothing here")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.post("/validate")
    async def validate(body: _Body) -> dict[str, int]:
        return {"v": body.secret_value}

    @app.post("/csrf", dependencies=[Depends(require_csrf)])
    async def csrf() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/csrf", dependencies=[Depends(require_csrf)])
    async def csrf_get() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/admin-only")
    async def admin_only(user: User = Depends(require_roles(Role.ADMIN))) -> dict[str, str]:  # noqa: B008
        return {"role": user.role.value}

    return app


def _user(role: Role) -> User:
    return User(id=uuid.uuid4(), role=role, display_name="X", password_hash="h")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = _build_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as c:
        c.app = app  # type: ignore[attr-defined]
        yield c


async def test_app_error_should_use_standard_shape_with_trace_id(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert body["error"]["message"] == "Nothing here"
    assert body["error"]["traceId"] == response.headers["x-trace-id"]


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("GET", "/no-such-route", 404, "RESOURCE_NOT_FOUND"),
        ("DELETE", "/boom", 405, "METHOD_NOT_ALLOWED"),
    ],
)
async def test_framework_http_errors_should_use_standard_shape(
    client: httpx.AsyncClient, method: str, path: str, status: int, code: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_unhandled_error_should_return_generic_500_without_leaking_details(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text


async def test_validation_error_should_name_field_but_not_echo_value(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/validate", json={"secret_value": "PRIVATE-TEXT"})

    assert response.status_code == 422
    assert "secret_value" in response.json()["error"]["message"]
    assert "PRIVATE-TEXT" not in response.text


async def test_should_honour_valid_incoming_trace_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/not-found", headers={"X-Request-ID": "abcd1234-trace"})

    assert response.headers["x-trace-id"] == "abcd1234-trace"


async def test_should_replace_malformed_incoming_trace_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/not-found", headers={"X-Trace-Id": "bad\nvalue"})

    assert response.headers["x-trace-id"] != "bad\nvalue"
    assert len(response.headers["x-trace-id"]) == 32


async def test_should_add_security_headers_to_error_responses(client: httpx.AsyncClient) -> None:
    response = await client.get("/no-such-route")

    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


async def test_cors_should_echo_only_allowed_origins(client: httpx.AsyncClient) -> None:
    allowed = await client.get("/not-found", headers={"Origin": "https://ok.test"})
    denied = await client.get("/not-found", headers={"Origin": "https://evil.test"})

    assert allowed.headers["access-control-allow-origin"] == "https://ok.test"
    assert "access-control-allow-origin" not in denied.headers


async def test_csrf_should_allow_safe_methods_without_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/csrf")).status_code == 200


@pytest.mark.parametrize(
    ("cookie", "header", "status"),
    [("tok", "tok", 200), ("tok", "other", 403), ("tok", None, 403), (None, "tok", 403)],
)
async def test_csrf_should_require_matching_cookie_and_header(
    client: httpx.AsyncClient, cookie: str | None, header: str | None, status: int
) -> None:
    if cookie:
        client.cookies.set("gc_csrf", cookie)
    headers = {"X-CSRF-Token": header} if header else {}

    response = await client.post("/csrf", headers=headers)

    assert response.status_code == status


@pytest.mark.parametrize(("role", "status"), [(Role.ADMIN, 200), (Role.STUDENT, 403)])
async def test_require_roles_should_gate_by_role(
    client: httpx.AsyncClient, role: Role, status: int
) -> None:
    client.app.dependency_overrides[current_user] = lambda: _user(role)  # type: ignore[attr-defined]

    response = await client.get("/admin-only")

    assert response.status_code == status


@pytest.mark.parametrize(
    ("now", "window", "expected"),
    [
        (datetime(2026, 1, 1, 12, 0, 59, tzinfo=UTC), 60, datetime(2026, 1, 1, 12, 0, tzinfo=UTC)),
        (datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC), 60, datetime(2026, 1, 1, 12, 1, tzinfo=UTC)),
        (datetime(2026, 1, 1, 12, 59, tzinfo=UTC), 3600, datetime(2026, 1, 1, 12, 0, tzinfo=UTC)),
    ],
)
def test_window_start_should_align_to_epoch(now: datetime, window: int, expected: datetime) -> None:
    assert window_start(now, window) == expected


def test_system_clock_should_return_aware_utc() -> None:
    assert get_clock().now().tzinfo is UTC
    assert isinstance(get_clock(), SystemClock)
