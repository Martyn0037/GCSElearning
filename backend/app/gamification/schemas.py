# backend/app/gamification/schemas.py
"""Response bodies for XP, streaks, badges, the home dashboard and challenges."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import ApiModel
from app.gamification.grading import Standing
from app.gamification.rings import Ring
from app.models.gamification import ChallengeKind, ChallengeStatus


class BadgeOut(ApiModel):
    """A badge, and when it was earned (null if not yet)."""

    code: str
    name: str
    description: str
    earned_at: datetime | None


class RewardsOut(ApiModel):
    """What an answer earned."""

    xp_gained: int = Field(description="XP for this answer")
    bonus_xp: int = Field(description="Challenge completion bonus earned with this answer")
    total_xp: int
    level: int
    level_up: bool
    xp_into_level: int
    xp_for_level: int = Field(description="XP from this level to the next (0 at the top)")
    streak_days: int
    streak_extended: bool = Field(description="First answer of a new day")
    used_freeze: bool = Field(description="This week's freeze covered a missed day")
    new_badges: list[BadgeOut]


class ChallengeProgressOut(ApiModel):
    """Where an answered question's challenge is up to."""

    challenge_id: uuid.UUID
    kind: ChallengeKind
    answered: int
    total: int
    completed: bool


class GradeEstimateOut(ApiModel):
    """An ESTIMATE from one short topic test, never a predicted grade.

    With grade boundaries: a two-grade band, e.g. 5-6. Without: only the
    percentage and how secure it is.
    """

    percent: float
    standing: Standing
    band_low: int | None
    band_high: int | None
    below_lowest_grade: int | None = Field(description="Set when under every boundary")


class ChallengeItemResultOut(ApiModel):
    """One question of a finished challenge, for going through afterwards."""

    position: int
    stem: str
    marks: int
    marks_earned: int
    answered: bool
    correct: bool | None
    your_answer: str | None
    correct_answer: str
    worked_solution: str


class ChallengeOut(ApiModel):
    """A daily challenge or boss battle."""

    id: uuid.UUID
    kind: ChallengeKind
    status: ChallengeStatus
    london_date: date
    total: int
    answered: int
    enrolment_id: uuid.UUID | None
    topic_id: uuid.UUID | None
    topic_title: str | None
    deadline_at: datetime | None
    seconds_left: int | None = Field(description="Boss battles: time left now")
    score: int | None
    max_score: int | None
    percent: float | None
    bonus_xp: int | None
    grade: GradeEstimateOut | None = Field(description="Boss battles, once finished")
    previous_best: float | None = Field(description="Boss battles: best earlier score, %")
    personal_best: bool
    results: list[ChallengeItemResultOut] = Field(description="Once finished")


class LevelOut(ApiModel):
    """Overall level and XP."""

    level: int
    total_xp: int
    xp_into_level: int
    xp_for_level: int


class StreakOut(ApiModel):
    """The daily streak as of today."""

    current_days: int
    longest_days: int
    active_today: bool
    freeze_available: bool = Field(description="This week's free missed day is unused")


class DailyStatusOut(ApiModel):
    """Today's daily challenge."""

    challenge_id: uuid.UUID | None
    status: Literal["not_started", "active", "completed"]
    answered: int
    total: int


class ContinueOut(ApiModel):
    """Where "Continue" goes: the next best thing to do."""

    kind: Literal["daily", "review", "topic", "none"]
    challenge_id: uuid.UUID | None = None
    enrolment_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    label: str


class DashboardOut(ApiModel):
    """Everything the student's home screen shows, in one request."""

    level: LevelOut
    streak: StreakOut
    xp_this_week: int
    xp_last_week: int
    daily: DailyStatusOut
    reviews_due: int
    continue_to: ContinueOut
    badges_earned: int
    badges_total: int
    recent_badges: list[BadgeOut]


class TopicStandingOut(ApiModel):
    """A topic's ring and boss battle status."""

    ring: Ring
    ring_progress: float = Field(description="0-1 towards the next ring")
    boss_unlocked: bool
    skills_to_unlock_boss: int
    boss_best: float | None


class GradeBoundaryIn(ApiModel):
    """One grade's minimum percentage."""

    grade: int = Field(ge=1, le=9)
    min_percent: float = Field(gt=0, le=100)


class GradeBoundariesIn(ApiModel):
    """Admin: the full set of boundaries for one spec and tier (replaces any existing)."""

    tier: Literal["foundation", "higher"] | None
    boundaries: list[GradeBoundaryIn] = Field(max_length=9)


class GradeBoundariesOut(ApiModel):
    """Boundaries for one spec, by tier ("untiered" for specs without tiers)."""

    specification_id: uuid.UUID
    tier: Literal["foundation", "higher"] | None
    boundaries: list[GradeBoundaryIn]
