# backend/tests/unit/test_gamification_rules.py
"""Pure gamification rules.

Covers:
- XP: scales with difficulty; wrong = 0; a quarter off per hint; full solution
  = 2; difficulty clamped; boss bonus range
- levels: thresholds, progress into a level, zero/negative totals, the top level
- streaks (London days): first day; same day repeated is a no-op; next day
  extends; one missed day uses the week's freeze; a second missed day in the
  same week resets; freeze renews the next week; two missed days reset; a clock
  going backwards is ignored; displayed streak (alive, frozen, broken); freeze
  availability; London dates across BST/GMT changes and midnight
- rings: thresholds, exam ready needs a 70%+ boss, ring progress
- grade estimate: standing only without boundaries; band in the middle, at the
  top and bottom of a tier; below every boundary; single boundary
- selection: daily ranking (weak, new, strong; per-topic cap with spares);
  spread; boss difficulty; difficulty fallbacks; boss time
- badges: rules and the catalogue matching migration 0005
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.gamification import badges, selection
from app.gamification.grading import Standing, estimate
from app.gamification.rings import Ring, next_ring_progress, ring_for
from app.gamification.streaks import (
    StreakState,
    current_streak,
    freeze_available,
    record_activity,
    week_start,
)
from app.gamification.xp import boss_bonus, level_for, xp_for_answer, xp_to_reach
from app.practice.review import london_today

# --------------------------------------------------------------------- XP


@pytest.mark.parametrize(
    ("difficulty", "correct", "hints", "xp"),
    [
        (1, True, 0, 10),
        (5, True, 0, 50),
        (3, False, 0, 0),
        (4, True, 1, 30),
        (4, True, 3, 10),
        (1, True, 3, 2),
        (5, True, 4, 2),
        (9, True, 0, 50),
        (0, True, 0, 10),
    ],
)
def test_should_award_xp_by_difficulty_and_hints(
    difficulty: int, correct: bool, hints: int, xp: int
) -> None:
    assert xp_for_answer(difficulty, correct, hints) == xp


def test_boss_bonus_should_range_from_20_to_100() -> None:
    assert (boss_bonus(0), boss_bonus(50), boss_bonus(100), boss_bonus(150)) == (20, 60, 100, 100)


@pytest.mark.parametrize(
    ("total", "level", "into", "span"),
    [(0, 1, 0, 100), (99, 1, 99, 100), (100, 2, 0, 200), (650, 4, 50, 400), (-5, 1, 0, 100)],
)
def test_should_turn_xp_into_a_level(total: int, level: int, into: int, span: int) -> None:
    info = level_for(total)
    assert (info.level, info.xp_into_level, info.xp_for_level) == (level, into, span)


def test_should_stop_at_the_top_level() -> None:
    info = level_for(xp_to_reach(99) + 10_000)
    assert (info.level, info.xp_for_level) == (99, 0)


# --------------------------------------------------------------------- streaks

MON = date(2026, 11, 9)  # a Monday


def _day(offset: int) -> date:
    return date.fromordinal(MON.toordinal() + offset)


def test_first_activity_should_start_a_streak() -> None:
    update = record_activity(StreakState(), MON)
    assert (update.state.current, update.state.longest, update.extended) == (1, 1, True)


def test_same_day_should_change_nothing() -> None:
    state = record_activity(StreakState(), MON).state
    update = record_activity(state, MON)
    assert (update.state, update.extended) == (state, False)


def test_clock_going_backwards_should_be_ignored() -> None:
    state = StreakState(3, 3, _day(2))
    assert record_activity(state, _day(1)).state == state


def test_next_day_should_extend() -> None:
    update = record_activity(StreakState(3, 5, MON), _day(1))
    assert (update.state.current, update.state.longest, update.used_freeze) == (4, 5, False)


def test_one_missed_day_should_use_the_weeks_freeze() -> None:
    # Arrange: active Monday, missed Tuesday
    update = record_activity(StreakState(3, 3, MON), _day(2))

    # Assert
    assert (update.state.current, update.used_freeze) == (4, True)
    assert update.state.freeze_used_week == MON


def test_second_missed_day_in_the_same_week_should_reset() -> None:
    state = StreakState(4, 4, _day(2), freeze_used_week=MON)  # freeze used Tuesday
    update = record_activity(state, _day(4))  # missed Thursday
    assert (update.state.current, update.state.longest, update.used_freeze) == (1, 4, False)


def test_freeze_should_renew_the_next_week() -> None:
    state = StreakState(4, 4, _day(7), freeze_used_week=MON)  # active next Monday
    update = record_activity(state, _day(9))  # missed next Tuesday
    assert (update.state.current, update.used_freeze) == (5, True)


def test_two_missed_days_should_reset() -> None:
    update = record_activity(StreakState(6, 6, MON), _day(3))
    assert (update.state.current, update.state.longest) == (1, 6)


@pytest.mark.parametrize(
    ("state", "today", "shown"),
    [
        (StreakState(), MON, 0),
        (StreakState(3, 3, MON), MON, 3),
        (StreakState(3, 3, MON), _day(1), 3),
        (StreakState(3, 3, MON), _day(2), 3),  # freeze would cover yesterday
        (StreakState(3, 3, MON, freeze_used_week=MON), _day(2), 0),
        (StreakState(3, 3, MON), _day(3), 0),
    ],
)
def test_should_show_the_streak_as_of_today(state: StreakState, today: date, shown: int) -> None:
    assert current_streak(state, today) == shown


def test_should_report_freeze_availability_per_week() -> None:
    state = StreakState(freeze_used_week=MON)
    assert (freeze_available(state, _day(6)), freeze_available(state, _day(7))) == (False, True)
    assert week_start(_day(6)) == MON


@pytest.mark.parametrize(
    ("instant", "london"),
    [
        (datetime(2026, 7, 1, 23, 30, tzinfo=UTC), date(2026, 7, 2)),  # BST: already tomorrow
        (datetime(2026, 12, 1, 23, 30, tzinfo=UTC), date(2026, 12, 1)),  # GMT: still today
        (datetime(2026, 3, 29, 0, 30, tzinfo=UTC), date(2026, 3, 29)),  # clocks go forward
        (datetime(2026, 10, 24, 23, 30, tzinfo=UTC), date(2026, 10, 25)),  # night clocks go back
    ],
)
def test_streak_days_should_follow_london_dates_across_dst(instant: datetime, london: date) -> None:
    # Arrange: active the London day before
    state = StreakState(1, 1, date.fromordinal(london.toordinal() - 1))

    # Act
    update = record_activity(state, london_today(instant))

    # Assert
    assert (update.state.current, update.state.last_active_on) == (2, london)


# --------------------------------------------------------------------- rings


@pytest.mark.parametrize(
    ("mastery", "boss", "ring"),
    [
        (0.2, None, Ring.NONE),
        (0.4, None, Ring.BRONZE),
        (0.6, None, Ring.SILVER),
        (0.85, None, Ring.GOLD),
        (0.85, 69.9, Ring.GOLD),
        (0.85, 70.0, Ring.EXAM_READY),
        (0.7, 100.0, Ring.SILVER),
    ],
)
def test_should_choose_the_ring(mastery: float, boss: float | None, ring: Ring) -> None:
    assert ring_for(mastery, boss) is ring


def test_should_measure_progress_to_the_next_ring() -> None:
    assert (next_ring_progress(0.2), next_ring_progress(0.5), next_ring_progress(0.9)) == (
        0.5,
        0.5,
        1.0,
    )


# --------------------------------------------------------------------- grades

HIGHER = {4: 20.0, 5: 35.0, 6: 50.0, 7: 65.0, 8: 78.0, 9: 88.0}


def test_should_give_only_a_standing_without_boundaries() -> None:
    result = estimate(85.0, {})
    assert (result.standing, result.band_low, result.band_high) == (Standing.SECURE, None, None)


@pytest.mark.parametrize(
    ("percent", "band", "standing"),
    [
        (55.0, (6, 7), Standing.DEVELOPING),
        (92.0, (8, 9), Standing.SECURE),
        (25.0, (4, 5), Standing.NOT_YET),
    ],
)
def test_should_estimate_a_two_grade_band(
    percent: float, band: tuple[int, int], standing: Standing
) -> None:
    result = estimate(percent, HIGHER)
    assert ((result.band_low, result.band_high), result.standing) == (band, standing)


def test_should_say_below_the_lowest_grade() -> None:
    result = estimate(10.0, HIGHER)
    assert (result.band_low, result.below_lowest_grade) == (None, 4)


def test_should_handle_a_single_boundary() -> None:
    result = estimate(60.0, {5: 50.0})
    assert (result.band_low, result.band_high) == (5, 5)


# --------------------------------------------------------------------- selection


def _candidate(topic: uuid.UUID, mastery: float, attempts: int, order: int) -> selection.Candidate:
    return selection.Candidate(uuid.uuid4(), uuid.uuid4(), topic, 1, mastery, attempts, order)


def test_daily_should_rank_weak_then_new_then_strong_and_mix_topics() -> None:
    # Arrange
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    strong = _candidate(t2, 0.9, 5, 0)
    new = _candidate(t2, 0.0, 0, 1)
    weakest = _candidate(t1, 0.3, 4, 2)
    weak = _candidate(t1, 0.5, 4, 3)
    third_t1 = _candidate(t1, 0.6, 4, 4)

    # Act
    ranked = selection.rank_daily([strong, new, weakest, weak, third_t1])

    # Assert: the third t1 skill waits behind the others as a spare
    assert ranked == [weakest, weak, new, strong, third_t1]


def test_spread_should_sample_the_whole_topic() -> None:
    items = [uuid.uuid4() for _ in range(12)]
    assert selection.spread(items, 4) == [items[0], items[3], items[6], items[9]]
    assert selection.spread(items[:3], 6) == items[:3]


@pytest.mark.parametrize(("level", "target"), [(1, 3), (3, 4), (5, 5)])
def test_boss_should_be_one_level_up_at_least_apply(level: int, target: int) -> None:
    assert selection.boss_difficulty(level) == target


def test_should_fall_back_to_the_nearest_levels() -> None:
    assert selection.difficulty_fallbacks(4) == [4, 3, 5, 2, 1]
    assert selection.difficulty_fallbacks(1) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(("marks", "minutes"), [(2, 5), (6, 9), (11, 17)])
def test_boss_time_should_be_exam_pace(marks: int, minutes: int) -> None:
    assert selection.boss_minutes(marks) == minutes


# --------------------------------------------------------------------- badges


def test_should_earn_badges_for_meaningful_behaviour() -> None:
    stats = badges.BadgeStats(
        fixed=10,
        answered=100,
        exam_style_unaided=True,
        longest_streak=5,
        daily_completed=7,
        best_boss_percent=50.0,
        exam_ready_topic=True,
    )
    assert badges.earned(stats) == {
        "first_fix",
        "fixed_10",
        "century",
        "exam_style",
        "streak_5",
        "daily_7",
        "boss_first",
        "exam_ready",
    }
    assert badges.earned(badges.BadgeStats()) == set()


def test_badge_catalogue_should_match_the_migration() -> None:
    # Arrange: load migration 0005 as a module
    path = Path(__file__).parents[2] / "alembic" / "versions" / "0005_gamification.py"
    spec = importlib.util.spec_from_file_location("migration_0005", path)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Assert
    assert [(b.code, b.name, b.description) for b in badges.CATALOGUE] == list(module.BADGES)
