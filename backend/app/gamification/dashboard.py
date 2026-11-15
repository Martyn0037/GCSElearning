# backend/app/gamification/dashboard.py
"""The student's home screen in one request: level, streak, today's
challenge, reviews due, where "Continue" goes, and badges."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification import badges as badge_rules
from app.gamification.schemas import (
    BadgeOut,
    ContinueOut,
    DailyStatusOut,
    DashboardOut,
    LevelOut,
    StreakOut,
)
from app.gamification.streaks import StreakState, current_streak, freeze_available, week_start
from app.gamification.xp import level_for
from app.models.curriculum import LearningObjective, Subtopic, Topic
from app.models.enrolment import StudentSubject
from app.models.gamification import (
    Badge,
    Challenge,
    ChallengeKind,
    ChallengeStatus,
    Streak,
    UserBadge,
    XpEvent,
)
from app.models.question import PracticeItem, Question
from app.practice.insights import review_summary
from app.practice.review import LONDON, london_today

RECENT_BADGES = 3


async def dashboard(session: AsyncSession, student_id: uuid.UUID, now: datetime) -> DashboardOut:
    """Everything the home screen shows. Read-only."""
    today = london_today(now)
    this_week = datetime.combine(week_start(today), time(), LONDON)
    last_week = this_week - timedelta(days=7)
    total, this_week_xp, last_week_xp = (
        await session.execute(
            select(
                func.coalesce(func.sum(XpEvent.amount), 0),
                func.coalesce(func.sum(XpEvent.amount).filter(XpEvent.created_at >= this_week), 0),
                func.coalesce(
                    func.sum(XpEvent.amount).filter(
                        XpEvent.created_at >= last_week, XpEvent.created_at < this_week
                    ),
                    0,
                ),
            ).where(XpEvent.user_id == student_id)
        )
    ).one()
    level = level_for(int(total))

    row = await session.get(Streak, student_id)
    state = (
        StreakState(row.current_days, row.longest_days, row.last_active_on, row.freeze_used_week)
        if row
        else StreakState()
    )
    streak = StreakOut(
        current_days=current_streak(state, today),
        longest_days=state.longest,
        active_today=state.last_active_on == today,
        freeze_available=freeze_available(state, today),
    )

    daily = await _daily_status(session, student_id, today)
    reviews_due = (await review_summary(session, student_id, now)).due_today
    badges_earned, recent = await _badges(session, student_id)
    return DashboardOut(
        level=LevelOut(
            level=level.level,
            total_xp=int(total),
            xp_into_level=level.xp_into_level,
            xp_for_level=level.xp_for_level,
        ),
        streak=streak,
        xp_this_week=int(this_week_xp),
        xp_last_week=int(last_week_xp),
        daily=daily,
        reviews_due=reviews_due,
        continue_to=await _continue(session, student_id, daily, reviews_due),
        badges_earned=badges_earned,
        badges_total=len(badge_rules.CATALOGUE),
        recent_badges=recent,
    )


async def _daily_status(
    session: AsyncSession, student_id: uuid.UUID, today: object
) -> DailyStatusOut:
    challenge = await session.scalar(
        select(Challenge).where(
            Challenge.user_id == student_id,
            Challenge.kind == ChallengeKind.DAILY,
            Challenge.london_date == today,
        )
    )
    if challenge is None:
        return DailyStatusOut(challenge_id=None, status="not_started", answered=0, total=0)
    total, answered = (
        await session.execute(
            select(func.count(), func.count(PracticeItem.answered_at)).where(
                PracticeItem.challenge_id == challenge.id
            )
        )
    ).one()
    return DailyStatusOut(
        challenge_id=challenge.id,
        status="completed" if challenge.status is ChallengeStatus.COMPLETED else "active",
        answered=answered,
        total=total,
    )


async def _continue(
    session: AsyncSession, student_id: uuid.UUID, daily: DailyStatusOut, reviews_due: int
) -> ContinueOut:
    """The next best thing: an unfinished daily challenge, then reviews, then the
    last topic practised (or the first topic)."""
    if daily.status == "active":
        return ContinueOut(
            kind="daily", challenge_id=daily.challenge_id, label="Carry on with today's challenge"
        )
    if reviews_due:
        return ContinueOut(
            kind="review", label=f"Review {reviews_due} mistake{'s' if reviews_due != 1 else ''}"
        )
    last = (
        await session.execute(
            select(PracticeItem.enrolment_id, Topic.id, Topic.title)
            .join(Question, Question.id == PracticeItem.question_id)
            .join(LearningObjective, LearningObjective.id == Question.objective_id)
            .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .where(
                PracticeItem.user_id == student_id,
                PracticeItem.challenge_id.is_(None),
                PracticeItem.mistake_id.is_(None),
                Topic.retired_at.is_(None),
            )
            .order_by(PracticeItem.served_at.desc())
            .limit(1)
        )
    ).first()
    if last is None:
        last = (
            await session.execute(
                select(StudentSubject.id, Topic.id, Topic.title)
                .join(Topic, Topic.specification_id == StudentSubject.specification_id)
                .where(StudentSubject.student_id == student_id, Topic.retired_at.is_(None))
                .order_by(StudentSubject.position, Topic.position)
                .limit(1)
            )
        ).first()
    if last is None:
        return ContinueOut(kind="none", label="Nothing to practise yet")
    enrolment_id, topic_id, title = last
    return ContinueOut(
        kind="topic", enrolment_id=enrolment_id, topic_id=topic_id, label=f"Practise {title}"
    )


async def _badges(session: AsyncSession, student_id: uuid.UUID) -> tuple[int, list[BadgeOut]]:
    rows = (
        await session.execute(
            select(Badge, UserBadge.awarded_at)
            .join(UserBadge, UserBadge.badge_code == Badge.code)
            .where(UserBadge.user_id == student_id)
            .order_by(UserBadge.awarded_at.desc(), Badge.position)
        )
    ).all()
    recent = [
        BadgeOut(code=b.code, name=b.name, description=b.description, earned_at=at)
        for b, at in rows[:RECENT_BADGES]
    ]
    return len(rows), recent


async def all_badges(session: AsyncSession, student_id: uuid.UUID) -> list[BadgeOut]:
    """Every badge in catalogue order, with when it was earned (or null)."""
    rows = (
        await session.execute(
            select(Badge, UserBadge.awarded_at)
            .outerjoin(
                UserBadge, and_(UserBadge.badge_code == Badge.code, UserBadge.user_id == student_id)
            )
            .order_by(Badge.position)
        )
    ).all()
    return [
        BadgeOut(code=b.code, name=b.name, description=b.description, earned_at=at)
        for b, at in rows
    ]
