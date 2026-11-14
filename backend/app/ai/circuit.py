# backend/app/ai/circuit.py
"""A small circuit breaker so a Claude outage fails fast instead of piling up waits.

State is per process (each API/worker process learns independently). That's
deliberate: it needs no shared store, and every process recovers on its own.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from app.core.clock import Clock


class CircuitState(StrEnum):
    """Closed: calls allowed. Open: calls refused. Half-open: one trial call allowed."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Opens after N consecutive failures; lets one trial through after a cool-down."""

    def __init__(self, clock: Clock, failure_threshold: int, reset_seconds: float) -> None:
        """Create a closed breaker.

        Args:
            clock: Time source.
            failure_threshold: Consecutive failures that open the circuit.
            reset_seconds: How long to stay open before allowing a trial call.
        """
        self._clock = clock
        self._threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """The current state (open turns half-open once the cool-down passes)."""
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock.now().timestamp() - self._opened_at >= self._reset_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    async def allow(self) -> bool:
        """Return whether a call may proceed now (reserves the half-open trial)."""
        async with self._lock:
            state = self.state
            if state is CircuitState.CLOSED:
                return True
            if state is CircuitState.HALF_OPEN and not self._trial_in_flight:
                self._trial_in_flight = True
                return True
            return False

    async def record_success(self) -> None:
        """A call succeeded: close the circuit."""
        async with self._lock:
            self._failures = 0
            self._opened_at = None
            self._trial_in_flight = False

    async def record_failure(self) -> None:
        """A call failed: count it, and open (or re-open) the circuit at the threshold."""
        async with self._lock:
            self._failures += 1
            self._trial_in_flight = False
            if self._failures >= self._threshold or self._opened_at is not None:
                self._opened_at = self._clock.now().timestamp()
