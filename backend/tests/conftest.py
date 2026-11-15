# backend/tests/conftest.py
"""Shared pytest fixtures.

Integration tests use a real PostgreSQL 16: the one at ``TEST_DATABASE_URL``
if set, otherwise a throwaway container started with testcontainers.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.clock import get_clock
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import create_app
from tests.fixtures.factories import FakeClock, make_settings

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_BASE_URL = "https://testserver"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """URL of an empty PostgreSQL database for this test session."""
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


def _alembic_config(database_url: str) -> Config:
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


@pytest.fixture(scope="session")
async def migrated_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Engine for a database migrated to head (once per session)."""
    config = _alembic_config(database_url)
    # Alembic's env.py calls asyncio.run, so run it off this event loop.
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


# Tables whose rows come from migrations, not from tests.
REFERENCE_TABLES = frozenset({"badges"})


@pytest.fixture
async def db_engine(migrated_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """The migrated engine, with every table emptied after each test.

    Reference data inserted by migrations (the badge catalogue) is kept.
    """
    yield migrated_engine
    tables = ", ".join(
        t.name for t in Base.metadata.sorted_tables if t.name not in REFERENCE_TABLES
    )
    async with migrated_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session for arranging and asserting test data."""
    async with AsyncSession(db_engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def clock() -> FakeClock:
    """A controllable clock injected into the app."""
    return FakeClock()


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Settings pointing at the test database."""
    return make_settings(database_url)


@pytest.fixture
async def app(
    db_engine: AsyncEngine, settings: Settings, clock: FakeClock
) -> AsyncIterator[FastAPI]:
    """The application with lifespan started and clock/settings overridden."""
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_clock] = lambda: clock
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client that keeps cookies, like a browser."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as c:
        yield c


@pytest.fixture
async def other_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A second browser with its own cookie jar."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as c:
        yield c
