# backend/app/gamification/streaks.py
"""Daily practice streaks in London calendar days, with one free freeze a week.

A day counts when at least one question is answered. Missing a single day is
covered automatically by that week's freeze (weeks start on Monday), so one
off day never resets the streak and there's nothing to "buy back". Missing two
or more days starts again from 1 without any telling-off.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta


def week_start(day: date) -> date:
    """Monday of ``day``'s week."""
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True, slots=True)
class StreakState:
    """A student's streak as stored."""

    current: int = 0
    longest: int = 0
    last_active_on: date | None = None
    freeze_used_week: date | None = None


@dataclass(frozen=True, slots=True)
class StreakUpdate:
    """The new state after a day's activity, and whether the freeze was used."""

    state: StreakState
    used_freeze: bool
    extended: bool  # the first activity of a new day


def record_activity(state: StreakState, today: date) -> StreakUpdate:
    """Count ``today`` as an active day.

    Repeated calls on the same day change nothing. A clock that goes backwards
    (``today`` before the last active day) is ignored rather than trusted.
    """
    last = state.last_active_on
    if last is not None and today <= last:
        return StreakUpdate(state, used_freeze=False, extended=False)
    used_freeze = False
    if last is None:
        current = 1
    else:
        gap = (today - last).days - 1  # days missed in between
        if gap == 0:
            current = state.current + 1
        elif gap == 1 and _freeze_free(state, last + timedelta(days=1)):
            current = state.current + 1
            used_freeze = True
        else:
            current = 1
    missed_day = (last + timedelta(days=1)) if last else None
    new = replace(
        state,
        current=current,
        longest=max(state.longest, current),
        last_active_on=today,
        freeze_used_week=week_start(missed_day)
        if used_freeze and missed_day
        else state.freeze_used_week,
    )
    return StreakUpdate(new, used_freeze=used_freeze, extended=True)


def _freeze_free(state: StreakState, missed_day: date) -> bool:
    return state.freeze_used_week != week_start(missed_day)


def current_streak(state: StreakState, today: date) -> int:
    """The streak to show today, without changing anything.

    It's still alive if he was active today or yesterday, or if exactly one
    day was missed and that week's freeze is still free.
    """
    last = state.last_active_on
    if last is None:
        return 0
    gap = (today - last).days - 1
    if gap <= 0:
        return state.current
    if gap == 1 and _freeze_free(state, last + timedelta(days=1)):
        return state.current
    return 0


def freeze_available(state: StreakState, today: date) -> bool:
    """Whether this week's freeze hasn't been used yet."""
    return state.freeze_used_week != week_start(today)
