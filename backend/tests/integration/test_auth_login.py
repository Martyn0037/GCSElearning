# backend/tests/integration/test_auth_login.py
"""Integration tests for POST /api/v1/auth/login.

Covers:
- happy path: student by username, guardian by email (case-insensitive)
- cookies: httpOnly/Secure/SameSite=Strict, scoped paths, CSRF cookie readable
- failures: wrong password, unknown user, inactive user — identical responses
- lockout: locks after N failures, rejects even the right password while
  locked, unlocks after the lockout period, counter resets on success
- failed attempts persist (audit rows written even though the request fails)
- rate limiting per IP with Retry-After
- strict validation: unknown fields and empty values rejected
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.core.config import Settings
from app.models.audit_log import AuditLog
from app.models.user import Role, User
from tests.fixtures.factories import FakeClock, create_user
from tests.integration.helpers import error_code, login

pytestmark = pytest.mark.integration


def _set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    return {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}


async def test_should_sign_in_student_by_username_and_return_user(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange
    student = await create_user(session, Role.STUDENT, identifier="sam10")

    # Act
    response = await login(client, "sam10")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": str(student.id),
        "role": "student",
        "displayName": "Sam",
        "username": "sam10",
        "email": None,
        "setupCompleted": False,
    }
    assert "accessTokenExpiresAt" in body


async def test_should_match_email_case_insensitively_for_guardian(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.GUARDIAN, identifier="parent@example.test")

    response = await login(client, "  Parent@Example.TEST ")

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "guardian"


async def test_should_set_hardened_cookies_on_login(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")

    response = await login(client, "sam10")

    cookies = _set_cookie_headers(response)
    access, refresh, csrf = cookies[ACCESS_COOKIE], cookies[REFRESH_COOKIE], cookies[CSRF_COOKIE]
    for header in (access, refresh, csrf):
        assert "Secure" in header
        assert "SameSite=strict" in header
    assert "HttpOnly" in access
    assert "Path=/api" in access
    assert "HttpOnly" in refresh
    assert "Path=/api/v1/auth" in refresh
    assert "HttpOnly" not in csrf


async def test_should_never_return_tokens_in_the_response_body(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")

    response = await login(client, "sam10")

    access, refresh = client.cookies.get(ACCESS_COOKIE), client.cookies.get(REFRESH_COOKIE)
    assert access
    assert access not in response.text
    assert refresh
    assert refresh not in response.text


@pytest.mark.parametrize("scenario", ["wrong_password", "unknown_user", "inactive_user"])
async def test_should_return_identical_generic_error_for_any_credential_failure(
    client: httpx.AsyncClient, session: AsyncSession, scenario: str
) -> None:
    # Arrange
    await create_user(session, Role.STUDENT, identifier="sam10")
    await create_user(session, Role.STUDENT, identifier="gone", is_active=False)
    identifier, password = {
        "wrong_password": ("sam10", "not-the-password"),
        "unknown_user": ("nobody", "whatever-password"),
        "inactive_user": ("gone", "correct-horse-battery"),
    }[scenario]

    # Act
    response = await login(client, identifier, password)

    # Assert
    assert response.status_code == 401
    assert error_code(response) == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"].startswith("That username/email and password")
    assert ACCESS_COOKIE not in client.cookies


async def test_should_lock_account_after_max_failures_and_reject_correct_password(
    client: httpx.AsyncClient, session: AsyncSession, settings: Settings
) -> None:
    # Arrange
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    for _ in range(settings.login_max_failures):
        await login(client, "sam10", "wrong-password")

    # Act
    response = await login(client, "sam10")

    # Assert
    assert response.status_code == 401
    await session.refresh(student)
    assert student.locked_until is not None


async def test_should_unlock_account_after_lockout_period(
    client: httpx.AsyncClient, session: AsyncSession, settings: Settings, clock: FakeClock
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    for _ in range(settings.login_max_failures):
        await login(client, "sam10", "wrong-password")

    clock.advance(seconds=settings.login_lockout_seconds + 1)
    response = await login(client, "sam10")

    assert response.status_code == 200


async def test_should_reset_failure_count_after_successful_login(
    client: httpx.AsyncClient, session: AsyncSession, settings: Settings
) -> None:
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    for _ in range(settings.login_max_failures - 1):
        await login(client, "sam10", "wrong-password")

    await login(client, "sam10")

    await session.refresh(student)
    assert student.failed_login_count == 0
    assert student.locked_until is None


async def test_should_persist_failed_attempt_audit_even_though_request_fails(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    student = await create_user(session, Role.STUDENT, identifier="sam10")

    await login(client, "sam10", "wrong-password")

    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "auth.login.failed")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].target_user_id == student.id
    assert rows[0].details == {"reason": "bad_password"}
    assert rows[0].ip_hash is not None
    assert "127.0.0.1" not in rows[0].ip_hash


async def test_should_rate_limit_login_attempts_per_ip(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    # Arrange: use distinct identifiers so only the IP limit applies.
    for i in range(settings.login_ip_limit_per_minute):
        await login(client, f"nobody{i}", "whatever-password")

    # Act
    response = await login(client, "nobody-final", "whatever-password")

    # Assert
    assert response.status_code == 429
    assert error_code(response) == "RATE_LIMITED"
    assert int(response.headers["retry-after"]) >= 1


async def test_should_allow_login_again_in_next_rate_limit_window(
    client: httpx.AsyncClient, session: AsyncSession, settings: Settings, clock: FakeClock
) -> None:
    await create_user(session, Role.STUDENT, identifier="sam10")
    for i in range(settings.login_ip_limit_per_minute + 1):
        await login(client, f"nobody{i}", "whatever-password")

    clock.advance(seconds=61)
    response = await login(client, "sam10")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"identifier": "sam10", "password": "x", "role": "admin"},
        {"identifier": "", "password": "x"},
        {"identifier": "sam10"},
        {"identifier": "sam10", "password": "x" * 129},
    ],
    ids=["unknown_field", "empty_identifier", "missing_password", "password_too_long"],
)
async def test_should_reject_malformed_login_body_without_echoing_values(
    client: httpx.AsyncClient, payload: dict[str, str]
) -> None:
    response = await client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"
    assert "x" * 20 not in response.text  # submitted values are never echoed


async def test_should_write_success_audit_event(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    student = await create_user(session, Role.STUDENT, identifier="sam10")

    await login(client, "sam10")

    count = await session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "auth.login.succeeded", AuditLog.actor_user_id == student.id)
    )
    assert count == 1


async def test_should_upgrade_outdated_password_hash_on_login(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    # Arrange: a hash made with weaker parameters than the current defaults.
    from argon2 import PasswordHasher

    student = await create_user(session, Role.STUDENT, identifier="sam10")
    student.password_hash = PasswordHasher(time_cost=1, memory_cost=8192).hash(
        "correct-horse-battery"
    )
    await session.commit()
    old_hash = student.password_hash

    # Act
    response = await login(client, "sam10")

    # Assert
    assert response.status_code == 200
    await session.refresh(student)
    assert student.password_hash != old_hash
    assert isinstance(student, User)
