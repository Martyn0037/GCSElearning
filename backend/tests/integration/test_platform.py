# backend/tests/integration/test_platform.py
"""Integration tests for health, metrics, migrations, seeding and DB constraints.

Covers:
- /health/live always ok; /health/ready ok with DB, 503 when DB unreachable
- /metrics exposes request counters labelled by route template
- migrations: downgrade to base and upgrade to head round-trip cleanly,
  and models match the migrated schema (no pending autogenerate diff)
- seed: idempotent upsert of the three accounts and the guardian link
- DB check constraints: student must have username and no email; lower-case only
- rate-limit purge deletes only expired windows
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.auth import rate_limit
from app.auth.rate_limit import RateLimit
from app.cli.seed_users import SeedAccount, link_guardian, upsert_account
from app.db.base import Base
from app.models.rate_limit import RateLimitCounter
from app.models.user import GuardianLink, Role, User
from tests.conftest import _alembic_config
from tests.fixtures.factories import FIXED_NOW, default_password_hash

pytestmark = pytest.mark.integration


async def test_live_should_return_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_should_return_ok_when_database_reachable(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}


async def test_ready_should_return_503_when_database_unreachable(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    # Arrange: swap in an engine pointing at a closed port.
    real_engine = app.state.engine
    app.state.engine = create_async_engine(
        "postgresql+asyncpg://x:y@127.0.0.1:1/none", connect_args={"timeout": 1}
    )
    try:
        # Act
        response = await client.get("/health/ready")
    finally:
        await app.state.engine.dispose()
        app.state.engine = real_engine

    # Assert
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "fail"}


async def test_metrics_should_count_requests_by_route_template(client: httpx.AsyncClient) -> None:
    await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert 'route="/api/v1/users/{user_id}"' in response.text
    assert "00000000-0000" not in response.text


async def test_migrations_should_round_trip_and_match_models(
    database_url: str, db_engine: AsyncEngine
) -> None:
    # Arrange
    config = _alembic_config(database_url)

    # Act
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    # Pooled connections cached query plans for the old tables; drop them.
    await db_engine.dispose()

    # Assert: no differences between the models and the migrated schema.
    async with db_engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync_conn: compare_metadata(
                MigrationContext.configure(sync_conn, opts={"compare_type": True}), Base.metadata
            )
        )
    assert diff == []


async def test_seed_should_be_idempotent(session: AsyncSession) -> None:
    accounts = [
        SeedAccount(Role.GUARDIAN, "Parent@Example.test", "Alex", "guardian-password-1"),
        SeedAccount(Role.STUDENT, "Sam10", "Sam", "student-password-1"),
    ]

    for _ in range(2):
        guardian = await upsert_account(session, accounts[0])
        student = await upsert_account(session, accounts[1])
        await link_guardian(session, guardian, student)
        await session.commit()

    assert await session.scalar(select(func.count()).select_from(User)) == 2
    assert await session.scalar(select(func.count()).select_from(GuardianLink)) == 1
    assert student.username == "sam10"
    assert guardian.email == "parent@example.test"


@pytest.mark.parametrize(
    ("username", "email"),
    [(None, None), ("sam", "sam@example.test"), ("Sam", None)],
    ids=["no_identifier", "student_with_email", "uppercase_username"],
)
async def test_db_should_reject_invalid_student_identifiers(
    session: AsyncSession, username: str | None, email: str | None
) -> None:
    session.add(
        User(
            role=Role.STUDENT,
            username=username,
            email=email,
            display_name="Sam",
            password_hash=default_password_hash(),
        )
    )

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_purge_should_delete_only_expired_rate_limit_windows(session: AsyncSession) -> None:
    rule = RateLimit(limit=100, window_seconds=60)
    await rate_limit.hit(session, "old", rule, FIXED_NOW - timedelta(hours=2))
    await rate_limit.hit(session, "new", rule, FIXED_NOW)

    deleted = await rate_limit.purge_expired(session, FIXED_NOW - timedelta(hours=1))

    remaining = (await session.execute(select(RateLimitCounter.key))).scalars().all()
    assert deleted == 1
    assert remaining == ["new"]
