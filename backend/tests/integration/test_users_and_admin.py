# backend/tests/integration/test_users_and_admin.py
"""Integration tests for user reads (ownership rules) and admin password reset.

Covers:
- /users/me requires a valid, unexpired access token for an active user
- ownership: a student cannot read another user (404, not 403);
  guardians read only linked students; admins read anyone
- invalid UUID path -> 422
- admin password reset: old password stops working, new one works,
  existing sessions are revoked, lockout cleared
- admin reset forbidden for student/guardian; non-student target -> 404;
  CSRF required; weak password rejected
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import ACCESS_COOKIE
from app.core.config import Settings
from app.models.refresh_token import RefreshToken
from app.models.user import Role, User
from tests.fixtures.factories import FakeClock, create_user, link
from tests.integration.helpers import csrf_headers, error_code, login

pytestmark = pytest.mark.integration


async def test_should_return_401_for_me_without_session(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


async def test_should_return_current_user_for_me(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "sam10")

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["username"] == "sam10"


async def test_should_reject_expired_access_token(
    client: httpx.AsyncClient, session: AsyncSession, clock: FakeClock, settings: Settings
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "sam10")
    clock.advance(seconds=settings.access_token_ttl_seconds + 1)

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert error_code(response) == "TOKEN_EXPIRED"


async def test_should_reject_tampered_access_token(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "sam10")
    token = client.cookies.get(ACCESS_COOKIE)
    assert token is not None
    client.cookies.set(ACCESS_COOKIE, token[:-2] + "xx", path="/api")

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert error_code(response) == "TOKEN_INVALID"


async def test_should_reject_access_for_user_deactivated_after_login(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "sam10")
    student.is_active = False
    await session.commit()

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401


async def test_student_should_not_read_another_users_data(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    await create_user(session, Role.STUDENT, identifier="sam10")
    other = await create_user(session, Role.STUDENT, identifier="other")
    guardian = await create_user(session, Role.GUARDIAN)
    await login(client, "sam10")

    # Act
    responses = [await client.get(f"/api/v1/users/{uid}") for uid in (other.id, guardian.id)]

    # Assert: 404 so IDs can't be probed.
    assert [r.status_code for r in responses] == [404, 404]


async def test_guardian_should_read_linked_student_only(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    guardian = await create_user(session, Role.GUARDIAN, identifier="parent@example.test")
    linked = await create_user(session, Role.STUDENT, identifier="sam10")
    unlinked = await create_user(session, Role.STUDENT, identifier="other")
    await link(session, guardian, linked)
    await login(client, "parent@example.test")

    ok = await client.get(f"/api/v1/users/{linked.id}")
    denied = await client.get(f"/api/v1/users/{unlinked.id}")

    assert ok.status_code == 200
    assert ok.json()["displayName"] == "Sam"
    assert denied.status_code == 404


async def test_admin_should_read_any_user(client: httpx.AsyncClient, session: AsyncSession) -> None:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    student = await create_user(session, Role.STUDENT)
    await login(client, "admin@example.test")

    response = await client.get(f"/api/v1/users/{student.id}")

    assert response.status_code == 200


async def test_admin_should_get_404_for_missing_user(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    await login(client, "admin@example.test")

    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_should_reject_non_uuid_user_id(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "sam10")

    response = await client.get("/api/v1/users/not-a-uuid")

    assert response.status_code == 422


async def _reset(
    client: httpx.AsyncClient, student_id: object, password: str = "a-brand-new-password"
) -> httpx.Response:
    return await client.post(
        f"/api/v1/admin/students/{student_id}/password",
        json={"newPassword": password},
        headers=csrf_headers(client),
    )


async def test_admin_should_reset_student_password_and_revoke_sessions(
    client: httpx.AsyncClient,
    other_client: httpx.AsyncClient,
    session: AsyncSession,
    settings: Settings,
) -> None:
    # Arrange: student is signed in on another device and partly locked out.
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    await login(other_client, "sam10")
    await login(other_client, "sam10", "wrong-password")
    await login(client, "admin@example.test")

    # Act
    response = await _reset(client, student.id)

    # Assert
    assert response.status_code == 204
    active = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.user_id == student.id, RefreshToken.revoked_at.is_(None)
        )
    )
    assert active is None
    assert (await login(other_client, "sam10")).status_code == 401
    assert (await login(other_client, "sam10", "a-brand-new-password")).status_code == 200


@pytest.mark.parametrize("role", [Role.STUDENT, Role.GUARDIAN])
async def test_non_admin_should_be_forbidden_from_resetting_passwords(
    client: httpx.AsyncClient, session: AsyncSession, role: Role
) -> None:
    actor = await create_user(session, role)
    target = await create_user(session, Role.STUDENT)
    await login(client, actor.username or actor.email or "")

    response = await _reset(client, target.id)

    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


async def test_admin_reset_should_404_when_target_is_not_a_student(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    guardian = await create_user(session, Role.GUARDIAN)
    await login(client, "admin@example.test")

    response = await _reset(client, guardian.id)

    assert response.status_code == 404


async def test_admin_reset_should_require_csrf(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    student = await create_user(session, Role.STUDENT)
    await login(client, "admin@example.test")

    response = await client.post(
        f"/api/v1/admin/students/{student.id}/password", json={"newPassword": "a-new-password-1"}
    )

    assert response.status_code == 403
    assert error_code(response) == "CSRF_FAILED"


async def test_admin_reset_should_reject_short_password(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    student = await create_user(session, Role.STUDENT)
    await login(client, "admin@example.test")

    response = await _reset(client, student.id, password="short")

    assert response.status_code == 422
    unchanged = await session.get(User, student.id)
    assert unchanged is not None
