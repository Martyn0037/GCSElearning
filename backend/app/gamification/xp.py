# backend/app/gamification/xp.py
"""How much XP an answer is worth, and what level a total reaches.

XP rewards getting things right, scaled by difficulty, and still rewards
using hints (less), so asking for help is never punished. Wrong answers earn
nothing, but cost nothing either: XP never goes down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

XP_PER_DIFFICULTY = 10
# Each of hints 1-3 takes a quarter off; after the full solution (hint 4)
# a correct answer earns a token amount.
HINT_PENALTY = 0.25
ASSISTED_XP = 2
DAILY_CHALLENGE_BONUS = 50
# Between 1 and 99 XP a level costs 50 more than the one before:
# level 2 at 100 XP, 3 at 300, 4 at 600, 5 at 1000, 10 at 4500.
LEVEL_STEP = 50
MAX_LEVEL = 99


def xp_for_answer(difficulty: int, correct: bool, hints_revealed: int) -> int:
    """XP for one answer.

    Args:
        difficulty: The question's level, 1-5.
        correct: Whether it was marked right.
        hints_revealed: Hints used (4 = the full worked solution).

    Returns:
        0 for a wrong answer; otherwise 10 per difficulty level, less a quarter
        per hint, and 2 after the full solution.
    """
    if not correct:
        return 0
    if hints_revealed >= 4:
        return ASSISTED_XP
    full = XP_PER_DIFFICULTY * max(1, min(difficulty, 5))
    return max(ASSISTED_XP, round(full * (1 - HINT_PENALTY * max(hints_revealed, 0))))


def boss_bonus(percent: float) -> int:
    """Completion bonus for a boss battle: 20 XP for finishing, plus up to 80 for the score."""
    return 20 + round(80 * max(0.0, min(percent, 100.0)) / 100)


def xp_to_reach(level: int) -> int:
    """Total XP at which ``level`` starts (level 1 starts at 0)."""
    return LEVEL_STEP * (level - 1) * level


@dataclass(frozen=True, slots=True)
class LevelInfo:
    """A total XP expressed as a level and progress through it."""

    level: int
    xp_into_level: int
    xp_for_level: int  # XP needed to go from this level to the next (0 at max)


def level_for(total_xp: int) -> LevelInfo:
    """The level reached with ``total_xp``, and progress towards the next."""
    total = max(total_xp, 0)
    # Solve 50·L·(L-1) <= total for the largest L, then correct for float error.
    level = int((1 + math.sqrt(1 + 4 * total / LEVEL_STEP)) / 2)
    while xp_to_reach(level + 1) <= total:
        level += 1
    while level > 1 and xp_to_reach(level) > total:
        level -= 1
    level = min(level, MAX_LEVEL)
    if level == MAX_LEVEL:
        return LevelInfo(level, total - xp_to_reach(level), 0)
    start = xp_to_reach(level)
    return LevelInfo(level, total - start, xp_to_reach(level + 1) - start)
