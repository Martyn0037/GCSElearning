# backend/app/auth/router.py
"""``/api/v1/auth`` endpoints: login, refresh, logout."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import JSONResponse

from app.auth import rate_limit
from app.auth.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from app.auth.dependencies import (
    IpHashDep,
    NowDep,
    SessionDep,
    SettingsDep,
    require_csrf,
)
from app.auth.rate_limit import RateLimit
from app.auth.schemas import LoginRequest, SessionOut, UserOut
from app.auth.service import AuthService, IssuedSession, normalise_identifier
from app.core.errors import AuthenticationError, error_body
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES

router = APIRouter(prefix=f"{API_V1_PREFIX}/auth", tags=["auth"], responses=ERROR_RESPONSES)

REFRESH_LIMIT = RateLimit(limit=30, window_seconds=60)
LOGIN_IDENTIFIER_LIMIT = RateLimit(limit=20, window_seconds=3600)


def _session_out(issued: IssuedSession) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(issued.user),
        access_token_expires_at=issued.access_expires_at,
    )


@router.post("/login", response_model=SessionOut, operation_id="login")
async def login(
    body: LoginRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    ip_hash: IpHashDep,
) -> SessionOut:
    """Sign in with a username (student) or email (guardian/admin).

    Rate-limited per IP and per account identifier, on top of the per-account
    lockout after repeated failures.
    """
    ip_rule = RateLimit(limit=settings.login_ip_limit_per_minute, window_seconds=60)
    await rate_limit.hit(session, f"login:ip:{ip_hash}", ip_rule, now)
    await rate_limit.hit(
        session, f"login:id:{normalise_identifier(body.identifier)}", LOGIN_IDENTIFIER_LIMIT, now
    )
    issued = await AuthService(session, settings, now).login(
        body.identifier, body.password, ip_hash
    )
    set_session_cookies(response, settings, issued, now)
    return _session_out(issued)


@router.post(
    "/refresh",
    response_model=SessionOut,
    operation_id="refreshSession",
    dependencies=[Depends(require_csrf)],
)
async def refresh(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    ip_hash: IpHashDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> SessionOut | JSONResponse:
    """Rotate the refresh token and issue a new access token."""
    await rate_limit.hit(session, f"refresh:ip:{ip_hash}", REFRESH_LIMIT, now)
    try:
        issued = await AuthService(session, settings, now).refresh(refresh_token, ip_hash)
    except AuthenticationError as exc:
        if exc.code == "REFRESH_RACE":
            raise
        # The refresh token is dead: clear the cookies so the client stops
        # retrying and goes to the login screen.
        failed = JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)
        clear_session_cookies(failed, settings)
        return failed
    set_session_cookies(response, settings, issued, now)
    return _session_out(issued)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="logout",
    dependencies=[Depends(require_csrf)],
)
async def logout(
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    """Sign out: revoke this session's refresh tokens and clear cookies. Idempotent."""
    await AuthService(session, settings, now).logout(refresh_token, actor_user_id=None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, settings)
    return response
