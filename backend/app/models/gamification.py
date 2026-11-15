# backend/app/models/gamification.py
"""XP, streaks, badges, daily challenges and boss battles, and grade boundaries (ADR-016)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.curriculum import TIER_ENUM, Tier


def _enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda e: [m.value for m in e])


class XpSource(StrEnum):
    """What earned the XP. With ``ref_id`` it makes each award unique."""

    ANSWER = "answer"  # ref: practice item
    DAILY_CHALLENGE = "daily_challenge"  # ref: challenge (completion bonus)
    BOSS_BATTLE = "boss_battle"  # ref: challenge (completion bonus)


class XpEvent(Base):
    """One XP award. Totals are summed from these, so history is never lost.

    ``(user_id, source, ref_id)`` is unique: a retried answer or a repeated
    "finish" can never pay out twice.
    """

    __tablename__ = "xp_events"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "ref_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_xp_events_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[XpSource] = mapped_column(_enum(XpSource, "xp_source"), nullable=False)
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Streak(Base):
    """A student's daily practice streak, in London calendar days."""

    __tablename__ = "streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    longest_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_active_on: Mapped[date | None] = mapped_column(Date)
    # Monday of the week whose freeze was last used (one freeze per week).
    freeze_used_week: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Badge(Base):
    """A badge that can be earned. Rows mirror ``app.gamification.badges.CATALOGUE``."""

    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class UserBadge(Base):
    """A badge a student has earned (once)."""

    __tablename__ = "user_badges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    badge_code: Mapped[str] = mapped_column(
        ForeignKey("badges.code", ondelete="CASCADE"), primary_key=True
    )
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChallengeKind(StrEnum):
    """Daily challenge (5 mixed questions) or boss battle (timed topic mini mock)."""

    DAILY = "daily"
    BOSS = "boss"


class ChallengeStatus(StrEnum):
    """A challenge is active until every question is answered or time runs out."""

    ACTIVE = "active"
    COMPLETED = "completed"


class Challenge(Base):
    """A daily challenge or boss battle. Its questions are practice items."""

    __tablename__ = "challenges"
    __table_args__ = (
        # One daily challenge per student per London day.
        Index(
            "uq_challenges_daily_per_day",
            "user_id",
            "london_date",
            unique=True,
            postgresql_where=text("kind = 'daily'"),
        ),
        # At most one boss battle in progress per topic.
        Index(
            "uq_challenges_active_boss_per_topic",
            "user_id",
            "topic_id",
            unique=True,
            postgresql_where=text("kind = 'boss' AND status = 'active'"),
        ),
        Index("ix_challenges_user_kind_topic", "user_id", "kind", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[ChallengeKind] = mapped_column(
        _enum(ChallengeKind, "challenge_kind"), nullable=False
    )
    status: Mapped[ChallengeStatus] = mapped_column(
        _enum(ChallengeStatus, "challenge_status"), nullable=False
    )
    london_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Boss battles only.
    enrolment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE")
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer)
    max_score: Mapped[int | None] = mapped_column(Integer)
    percent: Mapped[float | None] = mapped_column(Float)


class GradeBoundary(Base):
    """Minimum percentage for a grade on one spec (and tier), entered by the admin.

    Used only to estimate a grade band for boss battles; with none entered the
    app shows a percentage and "secure / developing / not yet" instead.
    """

    __tablename__ = "grade_boundaries"
    __table_args__ = (
        UniqueConstraint("specification_id", "tier", "grade", postgresql_nulls_not_distinct=True),
        CheckConstraint("grade BETWEEN 1 AND 9", name="grade_range"),
        CheckConstraint("min_percent > 0 AND min_percent <= 100", name="percent_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    specification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("specifications.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[Tier | None] = mapped_column(TIER_ENUM)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    min_percent: Mapped[float] = mapped_column(Float, nullable=False)
