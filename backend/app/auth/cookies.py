# backend/app/auth/cookies.py
"""Auth cookie names and how they are set and cleared.

- Access token: httpOnly, sent to all ``/api`` paths.
- Refresh token: httpOnly, sent only to ``/api/v1/auth`` so it isn't exposed
  on every request.
- CSRF token: readable by the frontend JavaScript (double-submit pattern), which
  echoes it in the ``X-CSRF-Token`` header on state-changing requests.

All are ``SameSite=Strict``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

from app.auth.service import IssuedSession
from app.auth.tokens import new_opaque_token
from app.core.config import Settings

ACCESS_COOKIE = "gc_access"
REFRESH_COOKIE = "gc_refresh"
CSRF_COOKIE = "gc_csrf"
CSRF_HEADER = "X-CSRF-Token"

ACCESS_PATH = "/api"
REFRESH_PATH = "/api/v1/auth"
CSRF_PATH = "/"


def _max_age(expires_at: datetime, now: datetime) -> int:
    return max(0, int((expires_at - now).total_seconds()))


def set_session_cookies(
    response: Response, settings: Settings, issued: IssuedSession, now: datetime
) -> None:
    """Write the access, refresh and a fresh CSRF cookie onto ``response``."""
    response.set_cookie(
        ACCESS_COOKIE,
        issued.access_token,
        max_age=_max_age(issued.access_expires_at, now),
        path=ACCESS_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=_max_age(issued.refresh_expires_at, now),
        path=REFRESH_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        new_opaque_token(),
        max_age=_max_age(issued.refresh_expires_at, now),
        path=CSRF_PATH,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Expire all auth cookies on ``response``."""
    for name, path, httponly in (
        (ACCESS_COOKIE, ACCESS_PATH, True),
        (REFRESH_COOKIE, REFRESH_PATH, True),
        (CSRF_COOKIE, CSRF_PATH, False),
    ):
        response.delete_cookie(
            name, path=path, secure=settings.cookie_secure, httponly=httponly, samesite="strict"
        )
