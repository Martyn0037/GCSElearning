# backend/app/guardian/schemas.py
"""Guardian request/response bodies."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import ApiModel
from app.gamification.rings import Ring

PRIVACY_POLICY_VERSION = "2026-11"
CONSENT_TYPE = "use_of_app"


class ConsentOut(ApiModel):
    """The guardian's current consent for a student (null fields if none)."""

    granted: bool
    policy_version: str | None
    granted_at: datetime | None


class LinkedStudentOut(ApiModel):
    """A student the guardian can see."""

    id: uuid.UUID
    display_name: str
    consent: ConsentOut
    current_policy_version: str


class ConsentIn(ApiModel):
    """Record consent under the privacy notice version shown."""

    policy_version: str = Field(max_length=32)


class WeakTopicOut(ApiModel):
    """A topic to work on."""

    title: str
    mastery: float
    ring: Ring


class SubjectWeekOut(ApiModel):
    """One subject's week."""

    subject_name: str
    answered: int
    correct: int
    weak_topics: list[WeakTopicOut]


class BossResultOut(ApiModel):
    """A boss battle finished this week."""

    topic_title: str | None
    percent: float | None


class WeeklySummaryOut(ApiModel):
    """A student's week (London, Monday to Sunday)."""

    student_id: uuid.UUID
    display_name: str
    week_start: date
    week_end: date
    answered: int
    correct: int
    minutes: int = Field(description="Approximate time answering (each question capped at 10 min)")
    active_days: list[date]
    xp: int
    streak_days: int
    mistakes_fixed: int
    badges: list[str]
    boss_battles: list[BossResultOut]
    subjects: list[SubjectWeekOut]


class DeleteStudentIn(ApiModel):
    """Confirmation for permanently deleting a student's account and data."""

    confirm: Literal["DELETE"]
    password: str = Field(min_length=1, max_length=200)
