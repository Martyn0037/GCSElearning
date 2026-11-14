# backend/app/auth/rate_limit.py
"""Fixed-window rate limiting stored in Postgres (ADR-004).

Counters live in the database rather than process memory, so limits hold
across restarts and across multiple API processes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RateLimitedError
from app.models.rate_limit import RateLimitCounter


@dataclass(frozen=True, slots=True)
class RateLimit:
    """At most ``limit`` requests per ``window_seconds`` for one key."""

    limit: int
    window_seconds: int


def window_start(now: datetime, window_seconds: int) -> datetime:
    """Return the start of the fixed window containing ``now``.

    Args:
        now: Aware datetime.
        window_seconds: Window length; windows are aligned to the Unix epoch.

    Returns:
        The aware start of the window.
    """
    epoch = int(now.timestamp())
    start = epoch - (epoch % window_seconds)
    return datetime.fromtimestamp(start, tz=now.tzinfo)


async def hit(session: AsyncSession, key: str, rule: RateLimit, now: datetime) -> None:
    """Count one request for ``key`` and reject it if the window is full.

    The increment is a single atomic upsert, so concurrent requests can't
    both slip under the limit. It commits immediately: a rejected request
    must still be counted even if the handler later rolls back.

    Args:
        session: Database session.
        key: What is being limited, e.g. ``login:ip:<hash>``.
        rule: The limit to apply.
        now: Current time.

    Raises:
        RateLimitedError: If this request exceeds the limit.
    """
    start = window_start(now, rule.window_seconds)
    stmt = (
        insert(RateLimitCounter)
        .values(key=key, window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    count = (await session.execute(stmt)).scalar_one()
    await session.commit()
    if count > rule.limit:
        retry_after = int((start + timedelta(seconds=rule.window_seconds) - now).total_seconds())
        raise RateLimitedError(retry_after)


async def purge_expired(session: AsyncSession, older_than: datetime) -> int:
    """Delete counters for windows that started before ``older_than``.

    Called periodically by the worker (Phase 3) to keep the table small.

    Returns:
        Number of rows deleted.
    """
    result = await session.execute(
        delete(RateLimitCounter).where(RateLimitCounter.window_start < older_than)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
