# backend/app/db/session.py
"""Async SQLAlchemy engine and per-request session management."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create a pooled async engine with a server-side statement timeout.

    Args:
        settings: Application settings.

    Returns:
        A configured engine. Dispose of it on shutdown.
    """
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "application_name": settings.service_name,
                "timezone": "UTC",
            },
            "timeout": 5,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory that doesn't expire objects on commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request.

    Services commit explicitly (unit of work) before returning, so a commit
    failure surfaces as an error response rather than after the response has
    been sent. Anything left uncommitted is rolled back when the session closes.

    Yields:
        An open session.
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
