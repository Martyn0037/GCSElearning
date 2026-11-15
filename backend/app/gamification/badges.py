# backend/app/gamification/badges.py
"""Badges for meaningful behaviour (fixing mistakes, streaks, hard questions),
never for simply logging in.

The catalogue here is the source of truth; migration 0005 inserts the same
rows into ``badges`` (a test checks they match).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BadgeDef:
    """A badge's code, name and how to earn it."""

    code: str
    name: str
    description: str


CATALOGUE: tuple[BadgeDef, ...] = (
    BadgeDef("first_fix", "First fix", "Fix your first mistake by getting it right twice."),
    BadgeDef("fixed_10", "Fixed 10 mistakes", "Fix 10 mistakes."),
    BadgeDef("fixed_50", "Fixed 50 mistakes", "Fix 50 mistakes."),
    BadgeDef("century", "Century", "Answer 100 questions."),
    BadgeDef(
        "exam_style", "Exam-style", "Get an exam-style (level 5) question right without hints."
    ),
    BadgeDef("streak_5", "5-day streak", "Practise on 5 days in a row."),
    BadgeDef("streak_30", "30-day streak", "Practise on 30 days in a row."),
    BadgeDef("daily_7", "Seven challenges", "Complete 7 daily challenges."),
    BadgeDef("boss_first", "Boss beaten", "Score 50% or more in a boss battle."),
    BadgeDef("exam_ready", "Exam ready", "Get a topic to Exam ready."),
)
BY_CODE = {badge.code: badge for badge in CATALOGUE}


@dataclass(frozen=True, slots=True)
class BadgeStats:
    """The numbers badge rules look at."""

    fixed: int = 0
    answered: int = 0
    exam_style_unaided: bool = False
    longest_streak: int = 0
    daily_completed: int = 0
    best_boss_percent: float | None = None
    exam_ready_topic: bool = False


def earned(stats: BadgeStats) -> set[str]:
    """Codes of every badge these stats qualify for."""
    rules = {
        "first_fix": stats.fixed >= 1,
        "fixed_10": stats.fixed >= 10,
        "fixed_50": stats.fixed >= 50,
        "century": stats.answered >= 100,
        "exam_style": stats.exam_style_unaided,
        "streak_5": stats.longest_streak >= 5,
        "streak_30": stats.longest_streak >= 30,
        "daily_7": stats.daily_completed >= 7,
        "boss_first": (stats.best_boss_percent or 0) >= 50,
        "exam_ready": stats.exam_ready_topic,
    }
    return {code for code, ok in rules.items() if ok}
