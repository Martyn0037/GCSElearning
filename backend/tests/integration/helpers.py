# backend/tests/integration/helpers.py
"""Helpers for driving the API like the frontend does."""

from __future__ import annotations

import httpx

from app.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from tests.fixtures.factories import DEFAULT_PASSWORD


async def login(
    client: httpx.AsyncClient, identifier: str, password: str = DEFAULT_PASSWORD
) -> httpx.Response:
    """POST the login form."""
    return await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Echo the CSRF cookie into the header, as the frontend does."""
    token = client.cookies.get(CSRF_COOKIE)
    return {CSRF_HEADER: token} if token else {}


async def refresh(client: httpx.AsyncClient) -> httpx.Response:
    """POST to the refresh endpoint with the CSRF header."""
    return await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))


def error_code(response: httpx.Response) -> str:
    """Return ``error.code`` from a standard error body."""
    return str(response.json()["error"]["code"])
