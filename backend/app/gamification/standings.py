# backend/app/gamification/standings.py
"""Per-topic rings and boss battle status for a student's subject."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.rings import Ring, next_ring_progress, ring_for
from app.models.curriculum import LearningObjective, Subtopic, Tier, Topic
from app.models.enrolment import StudentSubject
from app.models.gamification import Challenge, ChallengeKind, ChallengeStatus
from app.models.question import ObjectiveProgress
from app.practice.mastery import P_INIT


def on_tier(tier: Tier | None) -> ColumnElement[bool]:
    """Objectives that apply to a tier (Higher sees every statement)."""
    if tier is Tier.HIGHER:
        return LearningObjective.id.is_not(None)
    return LearningObjective.foundation_text.is_not(None)


@dataclass(frozen=True, slots=True)
class TopicStanding:
    """A topic's mastery, ring and boss battle status."""

    mastery: float
    ring: Ring
    ring_progress: float
    objectives_total: int
    objectives_practised: int
    boss_best: float | None

    @property
    def skills_to_unlock_boss(self) -> int:
        """Skills still to practise before the boss battle opens (half the topic)."""
        return max(0, math.ceil(self.objectives_total / 2) - self.objectives_practised)

    @property
    def boss_unlocked(self) -> bool:
        """The boss battle opens once half the topic's skills have been practised."""
        return self.objectives_total > 0 and self.skills_to_unlock_boss == 0


async def topic_standings(
    session: AsyncSession,
    enrolment: StudentSubject,
    topic_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, TopicStanding]:
    """Standing of every topic in the subject (or just ``topic_ids``), in two queries."""
    student_id = enrolment.student_id
    topic_filter = (
        Subtopic.topic_id.in_(topic_ids)
        if topic_ids is not None
        else Topic.specification_id == enrolment.specification_id
    )
    rows = (
        await session.execute(
            select(
                Subtopic.topic_id,
                func.count(LearningObjective.id),
                func.sum(func.coalesce(ObjectiveProgress.mastery, P_INIT)),
                func.count(case((ObjectiveProgress.attempts > 0, 1))),
            )
            .select_from(LearningObjective)
            .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .outerjoin(
                ObjectiveProgress,
                and_(
                    ObjectiveProgress.objective_id == LearningObjective.id,
                    ObjectiveProgress.user_id == student_id,
                ),
            )
            .where(
                topic_filter,
                Topic.retired_at.is_(None),
                Subtopic.retired_at.is_(None),
                LearningObjective.retired_at.is_(None),
                on_tier(enrolment.tier),
            )
            .group_by(Subtopic.topic_id)
        )
    ).all()
    best = await boss_bests(session, student_id, [topic_id for topic_id, *_ in rows])
    standings: dict[uuid.UUID, TopicStanding] = {}
    for topic_id, total, mastery_sum, practised in rows:
        mastery = round(float(mastery_sum) / total, 3) if total else 0.0
        standings[topic_id] = TopicStanding(
            mastery=mastery,
            ring=ring_for(mastery, best.get(topic_id)),
            ring_progress=next_ring_progress(mastery),
            objectives_total=total,
            objectives_practised=practised,
            boss_best=best.get(topic_id),
        )
    return standings


async def boss_bests(
    session: AsyncSession, student_id: uuid.UUID, topic_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float]:
    """Best finished boss battle score (%) per topic."""
    if not topic_ids:
        return {}
    rows = (
        await session.execute(
            select(Challenge.topic_id, func.max(Challenge.percent))
            .where(
                Challenge.user_id == student_id,
                Challenge.kind == ChallengeKind.BOSS,
                Challenge.status == ChallengeStatus.COMPLETED,
                Challenge.topic_id.in_(topic_ids),
            )
            .group_by(Challenge.topic_id)
        )
    ).all()
    return {topic_id: best for topic_id, best in rows if topic_id is not None and best is not None}
