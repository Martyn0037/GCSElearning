# backend/app/gamification/selection.py
"""Choosing questions for daily challenges and boss battles (pure rules)."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from app.gamification.rings import GOLD_AT

DAILY_SIZE = 5
DAILY_MAX_REVIEWS = 2
DAILY_PER_TOPIC = 2
BOSS_SIZE = 6
BOSS_MIN_QUESTIONS = 3
BOSS_MIN_DIFFICULTY = 3
BOSS_MINUTES_PER_MARK = 1.5
BOSS_MIN_MINUTES = 5
# Answers that arrive just after the deadline (slow network) still count.
BOSS_GRACE_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Candidate:
    """A skill the student could be asked about, with where they are on it."""

    objective_id: uuid.UUID
    enrolment_id: uuid.UUID
    topic_id: uuid.UUID
    level: int
    mastery: float
    attempts: int
    order: int  # subject, topic and spec order: lower comes first


def rank_daily(candidates: list[Candidate], per_topic: int = DAILY_PER_TOPIC) -> list[Candidate]:
    """Skills for the daily challenge, best first.

    Weak spots come first (practised but not yet gold, weakest first), then
    skills not tried yet (in spec order), then strong ones. At most
    ``per_topic`` from one topic come before any topic's next, so the
    challenge is mixed; the rest follow in the same order as spares in case
    some skills have no question ready.
    """
    weak = sorted(
        (c for c in candidates if c.attempts and c.mastery < GOLD_AT),
        key=lambda c: (c.mastery, c.order),
    )
    new = sorted((c for c in candidates if not c.attempts), key=lambda c: c.order)
    strong = sorted(
        (c for c in candidates if c.attempts and c.mastery >= GOLD_AT),
        key=lambda c: (c.mastery, c.order),
    )
    ranked = weak + new + strong
    first: list[Candidate] = []
    spare: list[Candidate] = []
    per: dict[uuid.UUID, int] = {}
    for candidate in ranked:
        if per.get(candidate.topic_id, 0) < per_topic:
            per[candidate.topic_id] = per.get(candidate.topic_id, 0) + 1
            first.append(candidate)
        else:
            spare.append(candidate)
    return first + spare


def spread(items: list[uuid.UUID], size: int = BOSS_SIZE) -> list[uuid.UUID]:
    """Up to ``size`` items evenly spaced through ``items``, keeping their order.

    A boss battle samples the whole topic, start to end, like a short paper.
    """
    if len(items) <= size:
        return list(items)
    step = len(items) / size
    return [items[math.floor(i * step)] for i in range(size)]


def boss_difficulty(level: int) -> int:
    """One level above where the student is, but always at least "apply" (3)."""
    return max(BOSS_MIN_DIFFICULTY, min(level + 1, 5))


def difficulty_fallbacks(target: int) -> list[int]:
    """Levels to try when the target has no question ready: nearest first, lower before higher."""
    order = [target]
    for distance in range(1, 5):
        order.extend(d for d in (target - distance, target + distance) if 1 <= d <= 5)
    return order


def boss_minutes(total_marks: int) -> int:
    """Time allowed: 1.5 minutes a mark (roughly exam pace), at least 5 minutes."""
    return max(BOSS_MIN_MINUTES, math.ceil(total_marks * BOSS_MINUTES_PER_MARK))
