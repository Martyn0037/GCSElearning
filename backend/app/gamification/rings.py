# backend/app/gamification/rings.py
"""Mastery rings per topic: bronze → silver → gold → exam ready.

A ring summarises the average BKT mastery over the topic's skills on the
student's tier (unpractised skills count at the prior, 0.2). "Exam ready"
also needs proof under exam conditions: a boss battle score of 70% or more.
"""

from __future__ import annotations

import itertools
from enum import StrEnum

BRONZE_AT = 0.4
SILVER_AT = 0.6
GOLD_AT = 0.8
EXAM_READY_BOSS_PERCENT = 70.0


class Ring(StrEnum):
    """A topic's mastery ring."""

    NONE = "none"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    EXAM_READY = "exam_ready"


def ring_for(mastery: float, best_boss_percent: float | None) -> Ring:
    """The ring for a topic's average mastery and best boss battle score."""
    if mastery >= GOLD_AT:
        if best_boss_percent is not None and best_boss_percent >= EXAM_READY_BOSS_PERCENT:
            return Ring.EXAM_READY
        return Ring.GOLD
    if mastery >= SILVER_AT:
        return Ring.SILVER
    if mastery >= BRONZE_AT:
        return Ring.BRONZE
    return Ring.NONE


def next_ring_progress(mastery: float) -> float:
    """How far (0-1) the topic is from its current ring towards the next one."""
    steps = [0.0, BRONZE_AT, SILVER_AT, GOLD_AT]
    for low, high in itertools.pairwise(steps):
        if mastery < high:
            return round((mastery - low) / (high - low), 3)
    return 1.0
