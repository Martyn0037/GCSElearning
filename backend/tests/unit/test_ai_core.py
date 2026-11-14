# backend/tests/unit/test_ai_core.py
"""Unit tests for pricing, the circuit breaker and budget periods.

Covers:
- cost includes cache reads/writes at their multipliers; worst case bounds it
- unknown model price is refused
- circuit: closed -> open after N failures -> half-open after reset with a
  single trial -> closed on success / re-opened on trial failure
- London day/month boundaries across BST/GMT
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ai.budget import period_starts
from app.ai.circuit import CircuitBreaker, CircuitState
from app.ai.pricing import TokenUsage, UnknownModelPriceError, cost_usd, worst_case_usd
from tests.fixtures.factories import FakeClock

PRICES = {"m": (Decimal("1.00"), Decimal("5.00"))}


def test_cost_should_price_cache_reads_and_writes() -> None:
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
    )

    assert cost_usd(PRICES, "m", usage) == Decimal("7.35")  # 1 + 5 + 0.1 + 1.25


def test_worst_case_should_bound_actual_cost() -> None:
    actual = cost_usd(
        PRICES, "m", TokenUsage(input_tokens=3000, output_tokens=8000, cache_read_tokens=1000)
    )

    assert worst_case_usd(PRICES, "m", 4000, 8000) >= actual


def test_unknown_model_should_be_refused() -> None:
    with pytest.raises(UnknownModelPriceError):
        cost_usd(PRICES, "other", TokenUsage())


async def test_circuit_should_open_after_threshold_failures() -> None:
    breaker = CircuitBreaker(FakeClock(), failure_threshold=2, reset_seconds=60)

    await breaker.record_failure()
    assert await breaker.allow() is True
    await breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    assert await breaker.allow() is False


async def test_circuit_should_allow_one_trial_after_reset_then_close_on_success() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(clock, failure_threshold=1, reset_seconds=60)
    await breaker.record_failure()
    clock.advance(seconds=61)

    first, second = await breaker.allow(), await breaker.allow()
    await breaker.record_success()

    assert (first, second) == (True, False)
    assert breaker.state is CircuitState.CLOSED


async def test_circuit_should_reopen_when_trial_fails() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(clock, failure_threshold=1, reset_seconds=60)
    await breaker.record_failure()
    clock.advance(seconds=61)
    await breaker.allow()

    await breaker.record_failure()

    assert breaker.state is CircuitState.OPEN


@pytest.mark.parametrize(
    ("now", "day", "month"),
    [
        # 23:30 UTC on 31 Mar 2026 is 00:30 BST on 1 April.
        (
            datetime(2026, 3, 31, 23, 30, tzinfo=UTC),
            "2026-04-01T00:00:00+01:00",
            "2026-04-01T00:00:00+01:00",
        ),
        # Winter: London = UTC.
        (
            datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            "2026-01-15T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    ],
    ids=["bst_rollover", "gmt"],
)
def test_budget_periods_should_follow_london_time(now: datetime, day: str, month: str) -> None:
    day_start, month_start = period_starts(now)

    assert day_start.isoformat() == day
    assert month_start.isoformat() == month
    assert now - day_start < timedelta(days=1)
