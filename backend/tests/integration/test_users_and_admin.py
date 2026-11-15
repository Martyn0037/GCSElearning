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
- admin student list: active students only, by name, with username and a
  current lock (an expired lock reads as null); admin only; limit bounded
- admin student update: name and/or username change, progress and sessions
  kept, new username signs in and the old one doesn't; audited; username
  normalised; taken username -> 409 USERNAME_TAKEN (also when two saves
  race); invalid name/username/empty body/unknown field -> 422; non-student
  -> 404; non-admin -> 403; CSRF required; saving the same values is a no-op
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import ACCESS_COOKIE
from app.core.config import Settings
from app.models.audit_log import AuditLog
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


async def test_admin_should_list_active_students_by_name_with_locks(
    client: httpx.AsyncClient, session: AsyncSession, clock: FakeClock
) -> None:
    # Arrange
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    zed = await create_user(session, Role.STUDENT, identifier="zed10", display_name="Zed")
    amy = await create_user(session, Role.STUDENT, identifier="amy10", display_name="Amy")
    gone = await create_user(session, Role.STUDENT, identifier="old10", display_name="Old")
    await create_user(session, Role.GUARDIAN, identifier="parent@example.test")
    zed.locked_until = clock.now() + timedelta(minutes=10)
    amy.locked_until = clock.now() - timedelta(minutes=1)  # expired
    gone.is_active = False
    await session.commit()
    await login(client, "admin@example.test")

    # Act
    response = await client.get("/api/v1/admin/students")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert [(s["displayName"], s["username"]) for s in body] == [("Amy", "amy10"), ("Zed", "zed10")]
    assert body[0]["lockedUntil"] is None
    assert body[1]["lockedUntil"] is not None
    assert body[0]["id"] == str(amy.id)


@pytest.mark.parametrize("role", [Role.STUDENT, Role.GUARDIAN])
async def test_non_admin_should_be_forbidden_from_listing_students(
    client: httpx.AsyncClient, session: AsyncSession, role: Role
) -> None:
    # Arrange
    identifier = "sam10" if role is Role.STUDENT else "parent@example.test"
    await create_user(session, role, identifier=identifier)
    await login(client, identifier)

    # Act
    response = await client.get("/api/v1/admin/students")

    # Assert
    assert response.status_code == 403


async def test_student_list_should_reject_an_out_of_range_limit(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    await login(client, "admin@example.test")

    # Act
    response = await client.get("/api/v1/admin/students", params={"limit": 0})

    # Assert
    assert response.status_code == 422


async def _update(client: httpx.AsyncClient, student_id: object, **body: object) -> httpx.Response:
    return await client.patch(
        f"/api/v1/admin/students/{student_id}", json=body, headers=csrf_headers(client)
    )


async def _admin_and_student(client: httpx.AsyncClient, session: AsyncSession) -> tuple[User, User]:
    admin = await create_user(session, Role.ADMIN, identifier="admin@example.test")
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    await login(client, "admin@example.test")
    return admin, student


async def test_admin_should_rename_student_and_change_username_keeping_sessions(
    client: httpx.AsyncClient, other_client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange: the student is signed in on another device.
    _, student = await _admin_and_student(client, session)
    await login(other_client, "sam10")

    # Act
    response = await _update(client, student.id, displayName="  Alex ", username=" Alex.K-10 ")

    # Assert
    assert response.status_code == 200
    assert response.json() == {
        "id": str(student.id),
        "displayName": "Alex",
        "username": "alex.k-10",
        "lockedUntil": None,
    }
    me = await other_client.get("/api/v1/users/me")
    assert (me.status_code, me.json()["displayName"]) == (200, "Alex")
    assert (await login(other_client, "sam10")).status_code == 401
    assert (await login(other_client, "alex.k-10")).status_code == 200
    events = (
        await session.scalars(select(AuditLog).where(AuditLog.action == "admin.student_updated"))
    ).all()
    assert [e.details for e in events] == [{"fields": ["display_name", "username"]}]


async def test_admin_should_change_only_the_name(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    _, student = await _admin_and_student(client, session)

    # Act
    response = await _update(client, student.id, displayName="Alex")

    # Assert
    assert response.status_code == 200
    assert (response.json()["displayName"], response.json()["username"]) == ("Alex", "sam10")


async def test_saving_the_same_values_should_change_nothing(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    _, student = await _admin_and_student(client, session)

    # Act
    response = await _update(client, student.id, displayName="Sam", username="sam10")

    # Assert
    assert response.status_code == 200
    events = (
        await session.scalars(select(AuditLog).where(AuditLog.action == "admin.student_updated"))
    ).all()
    assert events == []


async def test_taken_username_should_conflict(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    _, student = await _admin_and_student(client, session)
    await create_user(session, Role.STUDENT, identifier="kit10", display_name="Kit")

    # Act
    response = await _update(client, student.id, displayName="Alex", username="KIT10")

    # Assert: nothing changed, not even the name
    assert response.status_code == 409
    assert error_code(response) == "USERNAME_TAKEN"
    await session.refresh(student)
    assert (student.display_name, student.username) == ("Sam", "sam10")


async def test_two_saves_racing_for_one_username_should_leave_one_winner(
    client: httpx.AsyncClient,
    other_client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    # Arrange: two students, two admin sessions, both want "alex10".
    _, first = await _admin_and_student(client, session)
    second = await create_user(session, Role.STUDENT, identifier="kit10", display_name="Kit")
    await login(other_client, "admin@example.test")

    # Act
    responses = await asyncio.gather(
        _update(client, first.id, username="alex10"),
        _update(other_client, second.id, username="alex10"),
    )

    # Assert
    assert sorted(r.status_code for r in responses) == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert error_code(loser) == "USERNAME_TAKEN"
    owners = (await session.scalars(select(User).where(User.username == "alex10"))).all()
    assert len(owners) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"displayName": "   "},
        {"displayName": "x" * 41},
        {"displayName": "Al\u0007ex"},
        {"username": "ab"},
        {"username": "x" * 33},
        {"username": "alex@example.com"},
        {"username": "-alex"},
        {"username": "al ex"},
        {"displayName": "Alex", "role": "admin"},
    ],
    ids=[
        "empty",
        "blank_name",
        "long_name",
        "control_char",
        "short_username",
        "long_username",
        "email_like",
        "leading_hyphen",
        "space",
        "unknown_field",
    ],
)
async def test_invalid_update_should_be_rejected(
    client: httpx.AsyncClient, session: AsyncSession, body: dict[str, object]
) -> None:
    # Arrange
    _, student = await _admin_and_student(client, session)

    # Act
    response = await _update(client, student.id, **body)

    # Assert
    assert response.status_code == 422


async def test_updating_a_non_student_should_404(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    await _admin_and_student(client, session)
    guardian = await create_user(session, Role.GUARDIAN, identifier="parent@example.test")

    # Act
    response = await _update(client, guardian.id, displayName="Alex")

    # Assert
    assert response.status_code == 404


@pytest.mark.parametrize("role", [Role.STUDENT, Role.GUARDIAN])
async def test_non_admin_should_be_forbidden_from_updating_students(
    client: httpx.AsyncClient, session: AsyncSession, role: Role
) -> None:
    # Arrange
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    if role is Role.GUARDIAN:
        await create_user(session, role, identifier="parent@example.test")
    await login(client, "sam10" if role is Role.STUDENT else "parent@example.test")

    # Act
    response = await _update(client, student.id, displayName="Hacked")

    # Assert
    assert response.status_code == 403


async def test_student_update_should_require_csrf(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    _, student = await _admin_and_student(client, session)

    # Act
    response = await client.patch(
        f"/api/v1/admin/students/{student.id}", json={"displayName": "Alex"}
    )

    # Assert
    assert response.status_code == 403
