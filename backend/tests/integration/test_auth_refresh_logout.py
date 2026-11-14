# backend/tests/integration/test_auth_refresh_logout.py
"""Integration tests for refresh-token rotation and logout.

Covers:
- rotation issues new cookies and invalidates the old refresh token
- reuse of a rotated token after the grace window revokes the whole family
- reuse within the grace window (two tabs) is a benign race; family survives
- concurrency: two simultaneous refreshes with one token -> exactly one rotates
- expired / missing / unknown refresh tokens -> 401 and cookies cleared
- refresh fails for a deactivated user
- CSRF required on refresh and logout
- logout revokes the session and is idempotent
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.core.config import Settings
from app.models.refresh_token import RefreshToken
from app.models.user import Role
from tests.fixtures.factories import FakeClock, create_user
from tests.integration.helpers import csrf_headers, error_code, login, refresh

pytestmark = pytest.mark.integration


@pytest.fixture
async def signed_in(client: httpx.AsyncClient, session: AsyncSession) -> httpx.AsyncClient:
    """A client signed in as a student."""
    await create_user(session, Role.STUDENT, identifier="sam10")
    response = await login(client, "sam10")
    assert response.status_code == 200
    return client


def _copy_cookies(source: httpx.AsyncClient, target: httpx.AsyncClient) -> None:
    for cookie in source.cookies.jar:
        target.cookies.jar.set_cookie(cookie)


async def test_should_rotate_refresh_token_and_issue_new_cookies(
    signed_in: httpx.AsyncClient,
) -> None:
    old_refresh = signed_in.cookies.get(REFRESH_COOKIE)

    response = await refresh(signed_in)

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "sam10"
    assert signed_in.cookies.get(REFRESH_COOKIE) != old_refresh
    assert signed_in.cookies.get(ACCESS_COOKIE)


async def test_should_revoke_whole_family_when_rotated_token_is_reused_after_grace(
    signed_in: httpx.AsyncClient,
    other_client: httpx.AsyncClient,
    clock: FakeClock,
    settings: Settings,
) -> None:
    # Arrange: an attacker copies the cookies, then the real user refreshes.
    _copy_cookies(signed_in, other_client)
    assert (await refresh(signed_in)).status_code == 200
    clock.advance(seconds=settings.refresh_reuse_grace_seconds + 1)

    # Act: the attacker presents the stolen (now rotated) token.
    reuse = await refresh(other_client)

    # Assert: theft detected, and the real user's newer token is also dead.
    assert reuse.status_code == 401
    assert error_code(reuse) == "REFRESH_REUSED"
    legit = await refresh(signed_in)
    assert legit.status_code == 401


async def test_should_treat_reuse_within_grace_as_race_and_keep_family(
    signed_in: httpx.AsyncClient, other_client: httpx.AsyncClient
) -> None:
    _copy_cookies(signed_in, other_client)
    assert (await refresh(signed_in)).status_code == 200

    race = await refresh(other_client)

    assert race.status_code == 401
    assert error_code(race) == "REFRESH_RACE"
    assert (await refresh(signed_in)).status_code == 200


async def test_should_rotate_exactly_once_when_two_refreshes_race(
    signed_in: httpx.AsyncClient, other_client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    _copy_cookies(signed_in, other_client)

    # Act
    first, second = await asyncio.gather(refresh(signed_in), refresh(other_client))

    # Assert
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 401]
    loser = first if first.status_code == 401 else second
    assert error_code(loser) == "REFRESH_RACE"
    active = (
        (await session.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert len(active) == 1


async def test_should_reject_expired_refresh_token_and_clear_cookies(
    signed_in: httpx.AsyncClient, clock: FakeClock, settings: Settings
) -> None:
    clock.advance(seconds=settings.refresh_token_ttl_seconds + 1)

    response = await refresh(signed_in)

    assert response.status_code == 401
    assert error_code(response) == "REFRESH_EXPIRED"
    cleared = " ".join(response.headers.get_list("set-cookie"))
    assert f'{REFRESH_COOKIE}=""' in cleared or f"{REFRESH_COOKIE}=;" in cleared


async def test_should_reject_refresh_without_cookie(client: httpx.AsyncClient) -> None:
    client.cookies.set("gc_csrf", "abc")

    response = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "abc"})

    assert response.status_code == 401
    assert error_code(response) == "REFRESH_MISSING"


async def test_should_reject_unknown_refresh_token(client: httpx.AsyncClient) -> None:
    client.cookies.set("gc_csrf", "abc")
    client.cookies.set(REFRESH_COOKIE, "forged-token", path="/api/v1/auth")

    response = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "abc"})

    assert response.status_code == 401
    assert error_code(response) == "REFRESH_INVALID"


async def test_should_reject_refresh_for_deactivated_user(
    signed_in: httpx.AsyncClient, session: AsyncSession
) -> None:
    from app.models.user import User

    user = await session.scalar(select(User).where(User.username == "sam10"))
    assert user is not None
    user.is_active = False
    await session.commit()

    response = await refresh(signed_in)

    assert response.status_code == 401
    assert error_code(response) == "REFRESH_INVALID"


@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/logout"])
async def test_should_require_csrf_header_on_session_endpoints(
    signed_in: httpx.AsyncClient, path: str
) -> None:
    response = await signed_in.post(path, headers={"X-CSRF-Token": "wrong"})

    assert response.status_code == 403
    assert error_code(response) == "CSRF_FAILED"


async def test_should_revoke_session_on_logout_so_refresh_fails(
    signed_in: httpx.AsyncClient, other_client: httpx.AsyncClient
) -> None:
    # Arrange: keep a copy of the refresh token to try after logout.
    _copy_cookies(signed_in, other_client)

    # Act
    response = await signed_in.post("/api/v1/auth/logout", headers=csrf_headers(signed_in))

    # Assert
    assert response.status_code == 204
    assert signed_in.cookies.get(ACCESS_COOKIE) is None
    assert (await refresh(other_client)).status_code == 401


async def test_should_make_logout_idempotent(signed_in: httpx.AsyncClient) -> None:
    headers = csrf_headers(signed_in)
    await signed_in.post("/api/v1/auth/logout", headers=headers)
    signed_in.cookies.set("gc_csrf", headers["X-CSRF-Token"])

    response = await signed_in.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 204
