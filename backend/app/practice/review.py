# backend/app/practice/review.py
"""Spaced review of mistakes (ADR-006), behind an interface so FSRS can replace it.

Days are calendar days in Europe/London: a mistake made at 23:30 is due
"tomorrow" in London, not 24 hours later, and DST changes don't shift it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def london_today(now: datetime) -> date:
    """The calendar date in London at ``now``."""
    return now.astimezone(LONDON).date()


@dataclass(frozen=True, slots=True)
class ReviewState:
    """Where a mistake is in its review schedule."""

    stage: int
    correct_streak: int
    next_review_on: date
    resolved: bool = False


class ReviewScheduler(Protocol):
    """Decides when a mistake comes back."""

    def start(self, today: date) -> ReviewState:
        """Schedule a new (or repeated) mistake."""
        ...

    def after_review(self, state: ReviewState, correct: bool, today: date) -> ReviewState:
        """Reschedule after the student answers a review."""
        ...


class FixedIntervalScheduler:
    """Bring a mistake back after 1, 3, 7 and 14 days until it's right twice in a row.

    - Right: streak + 1; resolved at ``required_streak``; otherwise the next,
      longer interval.
    - Wrong: back to the start (1 day), streak reset.
    """

    def __init__(
        self, intervals: tuple[int, ...] = (1, 3, 7, 14), required_streak: int = 2
    ) -> None:
        """Create the scheduler.

        Args:
            intervals: Days until each successive review.
            required_streak: Correct reviews in a row that resolve the mistake.
        """
        if not intervals or required_streak < 1:
            raise ValueError("need at least one interval and a positive streak")
        self._intervals = intervals
        self._required = required_streak

    def start(self, today: date) -> ReviewState:
        """See :meth:`ReviewScheduler.start`."""
        return ReviewState(
            stage=0, correct_streak=0, next_review_on=today + timedelta(days=self._intervals[0])
        )

    def after_review(self, state: ReviewState, correct: bool, today: date) -> ReviewState:
        """See :meth:`ReviewScheduler.after_review`."""
        if not correct:
            return self.start(today)
        streak = state.correct_streak + 1
        if streak >= self._required:
            return ReviewState(state.stage, streak, state.next_review_on, resolved=True)
        stage = min(state.stage + 1, len(self._intervals) - 1)
        return ReviewState(stage, streak, today + timedelta(days=self._intervals[stage]))
