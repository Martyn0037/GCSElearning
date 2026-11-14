# backend/app/core/clock.py
"""Injectable clock so time-dependent logic is deterministic in tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...


class SystemClock:
    """Clock backed by the system time."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


def get_clock() -> Clock:
    """FastAPI dependency returning the system clock; overridden in tests."""
    return SystemClock()
