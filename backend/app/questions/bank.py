# backend/app/questions/bank.py
"""Choosing questions from the bank, and keeping the bank topped up ahead of the student.

The worker generates questions in the background for the objectives a student
can currently practise (at their level and the next), so they rarely wait.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue
from app.models.curriculum import LearningObjective, Subtopic, Tier, Topic
from app.models.enrolment import StudentSubject, StudentTopicSetting
from app.models.question import ObjectiveProgress, PracticeItem, Question, QuestionStatus

GENERATE_JOB = "generate_question"


def _tier_filter(tier: Tier | None):  # type: ignore[no-untyped-def]
    return Question.tier.is_(None) if tier is None else Question.tier == tier


async def pick_question(
    session: AsyncSession,
    user_id: uuid.UUID,
    objective_id: uuid.UUID,
    tier: Tier | None,
    difficulty: int,
) -> Question | None:
    """Best active question: never seen by this student first, else least recently seen."""
    last_seen = (
        select(PracticeItem.question_id, func.max(PracticeItem.served_at).label("seen"))
        .where(PracticeItem.user_id == user_id)
        .group_by(PracticeItem.question_id)
        .subquery()
    )
    return await session.scalar(
        select(Question)
        .outerjoin(last_seen, last_seen.c.question_id == Question.id)
        .where(
            Question.objective_id == objective_id,
            Question.difficulty == difficulty,
            Question.status == QuestionStatus.ACTIVE,
            _tier_filter(tier),
        )
        .order_by(last_seen.c.seen.asc().nulls_first(), Question.created_at)
        .limit(1)
    )


async def unseen_count(
    session: AsyncSession,
    user_id: uuid.UUID,
    objective_id: uuid.UUID,
    tier: Tier | None,
    difficulty: int,
) -> int:
    """Active questions at this level the student hasn't been served yet."""
    seen = select(PracticeItem.question_id).where(PracticeItem.user_id == user_id)
    count = await session.scalar(
        select(func.count())
        .select_from(Question)
        .where(
            Question.objective_id == objective_id,
            Question.difficulty == difficulty,
            Question.status == QuestionStatus.ACTIVE,
            _tier_filter(tier),
            Question.id.not_in(seen),
        )
    )
    return int(count or 0)


def generation_dedupe_key(objective_id: uuid.UUID, tier: Tier | None, difficulty: int) -> str:
    """One pending generation job per objective, tier and level."""
    return f"gen:{objective_id}:{tier.value if tier else '-'}:{difficulty}"


async def request_generation(
    session: AsyncSession,
    objective_id: uuid.UUID,
    tier: Tier | None,
    difficulty: int,
    now: datetime,
) -> bool:
    """Queue a background generation job (no-op if one is already pending). Caller commits."""
    return await enqueue(
        session,
        GENERATE_JOB,
        {
            "objective_id": str(objective_id),
            "tier": tier.value if tier else None,
            "difficulty": difficulty,
        },
        now,
        dedupe_key=generation_dedupe_key(objective_id, tier, difficulty),
    )


async def plan_top_up(session: AsyncSession, now: datetime, target: int) -> int:
    """Queue generation wherever a student is short of unseen questions (commits).

    Covers every active subject's topics that are covered at school, at the
    student's current level for each objective and the level above.

    Returns:
        Number of jobs queued.
    """
    rows = (
        await session.execute(
            select(
                StudentSubject.student_id,
                StudentSubject.tier,
                LearningObjective,
                ObjectiveProgress.level,
            )
            .join(Topic, Topic.specification_id == StudentSubject.specification_id)
            .join(
                StudentTopicSetting,
                and_(
                    StudentTopicSetting.topic_id == Topic.id,
                    StudentTopicSetting.student_id == StudentSubject.student_id,
                    StudentTopicSetting.taught_at_school.is_(True),
                ),
            )
            .join(Subtopic, Subtopic.topic_id == Topic.id)
            .join(LearningObjective, LearningObjective.subtopic_id == Subtopic.id)
            .outerjoin(
                ObjectiveProgress,
                and_(
                    ObjectiveProgress.objective_id == LearningObjective.id,
                    ObjectiveProgress.user_id == StudentSubject.student_id,
                ),
            )
            .where(
                StudentSubject.specification_id.is_not(None),
                Topic.retired_at.is_(None),
                LearningObjective.retired_at.is_(None),
            )
        )
    ).all()
    queued = 0
    # One count per objective/level: bounded by the objectives in topics covered
    # at school (tens to low hundreds), and it runs in the worker, not a request.
    for student_id, tier, objective, level in rows:
        if objective.text_for(tier) is None:
            continue  # not on this student's tier
        current = level or 1
        for difficulty in sorted({current, min(current + 1, 5)}):
            if await unseen_count(session, student_id, objective.id, tier, difficulty) < target:
                queued += await request_generation(session, objective.id, tier, difficulty, now)
    await session.commit()
    return queued
