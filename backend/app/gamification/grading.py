# backend/app/gamification/grading.py
"""Estimated grade band for a boss battle score.

A short topic test can't predict a GCSE grade precisely, so the estimate is
always a two-grade band ("around 5-6") and clearly labelled as an estimate.
Boundaries are entered by the admin per spec and tier (ADR-016); without them
only the percentage and a plain description are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SECURE_AT = 80.0
DEVELOPING_AT = 50.0


class Standing(StrEnum):
    """Plain-language description of a score."""

    SECURE = "secure"
    DEVELOPING = "developing"
    NOT_YET = "not_yet"


@dataclass(frozen=True, slots=True)
class GradeEstimate:
    """A score's description and, when boundaries exist, a grade band."""

    percent: float
    standing: Standing
    band_low: int | None = None
    band_high: int | None = None
    below_lowest_grade: int | None = None  # set when under every boundary


def standing_for(percent: float) -> Standing:
    """Secure (80%+), developing (50%+) or not yet."""
    if percent >= SECURE_AT:
        return Standing.SECURE
    if percent >= DEVELOPING_AT:
        return Standing.DEVELOPING
    return Standing.NOT_YET


def estimate(percent: float, boundaries: dict[int, float]) -> GradeEstimate:
    """Estimate a grade band from ``percent`` and ``{grade: min_percent}``.

    The band is the grade reached and the one above (or below, at the top of
    the scale for this tier): e.g. 62% with grade 5 at 55% and 6 at 65% gives
    "around 5-6".
    """
    standing = standing_for(percent)
    if not boundaries:
        return GradeEstimate(percent, standing)
    reached = [grade for grade, minimum in boundaries.items() if percent >= minimum]
    if not reached:
        return GradeEstimate(percent, standing, below_lowest_grade=min(boundaries))
    grade = max(reached)
    top = max(boundaries)
    low, high = (
        (grade - 1, grade) if grade == top and grade > min(boundaries) else (grade, grade + 1)
    )
    if high > top:
        low, high = grade, grade
    return GradeEstimate(percent, standing, band_low=low, band_high=high)
