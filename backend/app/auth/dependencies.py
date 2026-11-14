# backend/app/auth/dependencies.py
"""FastAPI dependencies for authentication, roles, CSRF and resource ownership."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.audit import hash_ip
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER
from app.auth.tokens import decode_access_token, tokens_match
from app.core.clock import Clock, get_clock
from app.core.config import Settings, get_settings
from app.core.errors import AppError, AuthenticationError, NotFoundError, PermissionDeniedError
from app.db.session import get_session
from app.models.user import GuardianLink, Role, User

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def request_now(clock: ClockDep) -> datetime:
    """Return one fixed 'now' for the whole request."""
    return clock.now()


NowDep = Annotated[datetime, Depends(request_now)]


def client_ip_hash(request: Request, settings: SettingsDep) -> str | None:
    """Return the hashed client IP (uvicorn resolves it from trusted proxy headers)."""
    host = request.client.host if request.client else None
    return hash_ip(host, settings.audit_ip_salt.get_secret_value())


IpHashDep = Annotated[str | None, Depends(client_ip_hash)]


def require_csrf(request: Request) -> None:
    """Reject state-changing requests whose CSRF header doesn't match the cookie.

    Raises:
        AppError: 403 ``CSRF_FAILED`` on mismatch.
    """
    if request.method in _SAFE_METHODS:
        return
    if not tokens_match(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise AppError(403, "CSRF_FAILED", "Your session needs refreshing. Please try again.")


async def current_user(
    request: Request, session: SessionDep, settings: SettingsDep, now: NowDep
) -> User:
    """Authenticate the request from the access-token cookie.

    The user is re-loaded from the database so that deactivated accounts and
    role changes take effect immediately, not when the token expires.

    Raises:
        AuthenticationError: If the token is missing/invalid or the user is gone
            or inactive.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthenticationError()
    claims = decode_access_token(settings, token, now)
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Please sign in again", code="TOKEN_INVALID")
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]


def require_roles(*roles: Role) -> Callable[[User], Awaitable[User]]:
    """Build a dependency that allows only the given roles.

    Args:
        *roles: Roles permitted to call the endpoint.

    Returns:
        A dependency returning the authenticated user.
    """
    allowed = frozenset(roles)

    async def _dependency(user: CurrentUserDep) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError()
        return user

    return _dependency


async def can_access_user(session: AsyncSession, actor: User, target_id: uuid.UUID) -> bool:
    """Return whether ``actor`` may read data belonging to ``target_id``.

    Rules: admins may read anyone; everyone may read themselves; guardians may
    read only the students they are linked to.
    """
    if actor.role is Role.ADMIN or actor.id == target_id:
        return True
    if actor.role is Role.GUARDIAN:
        link = await session.scalar(
            select(GuardianLink.student_id).where(
                GuardianLink.guardian_id == actor.id, GuardianLink.student_id == target_id
            )
        )
        return link is not None
    return False


async def ensure_can_access_user(session: AsyncSession, actor: User, target_id: uuid.UUID) -> None:
    """Raise unless ``actor`` may read ``target_id``'s data.

    Unauthorised access returns 404, not 403, so callers can't probe which
    user IDs exist.

    Raises:
        NotFoundError: If access is not allowed.
    """
    if not await can_access_user(session, actor, target_id):
        raise NotFoundError("User not found")
