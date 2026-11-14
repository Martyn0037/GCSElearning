# backend/tests/fixtures/factories.py
"""Test data factories and shared fake collaborators."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.core.config import Environment, Settings
from app.models.user import GuardianLink, Role, User

DEFAULT_PASSWORD = "correct-horse-battery"
FIXED_NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


@lru_cache(maxsize=1)
def default_password_hash() -> str:
    """Hash the default password once per test run (Argon2 is deliberately slow)."""
    return hash_password(DEFAULT_PASSWORD)


def make_settings(
    database_url: str = "postgresql+asyncpg://u:p@localhost/db", **overrides: object
) -> Settings:
    """Build settings for tests without reading any ``.env`` file."""
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "database_url": database_url,
        "jwt_secret": "test-jwt-secret-" + "x" * 32,
        "audit_ip_salt": "test-ip-salt-" + "y" * 32,
        "cors_origins": ["https://app.example.test"],
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@dataclass
class FakeClock:
    """A clock tests can move forward."""

    current: datetime = field(default_factory=lambda: FIXED_NOW)

    def now(self) -> datetime:
        """Return the fake current time."""
        return self.current

    def advance(self, **kwargs: float) -> None:
        """Move time forward by a ``timedelta(**kwargs)``."""
        self.current += timedelta(**kwargs)


async def create_user(
    session: AsyncSession,
    role: Role = Role.STUDENT,
    *,
    identifier: str | None = None,
    display_name: str = "Sam",
    is_active: bool = True,
) -> User:
    """Insert a user with the default password and commit.

    Args:
        session: Database session.
        role: Role for the user.
        identifier: Username (student) or email (others); random if omitted.
        display_name: First name / nickname.
        is_active: Whether the account can sign in.

    Returns:
        The committed user.
    """
    suffix = uuid.uuid4().hex[:8]
    if role is Role.STUDENT:
        username, email = (identifier or f"student{suffix}"), None
    else:
        username, email = None, (identifier or f"{role.value}{suffix}@example.test")
    user = User(
        role=role,
        username=username,
        email=email,
        display_name=display_name,
        password_hash=default_password_hash(),
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user


async def link(session: AsyncSession, guardian: User, student: User) -> None:
    """Link a guardian to a student and commit."""
    session.add(GuardianLink(guardian_id=guardian.id, student_id=student.id))
    await session.commit()
