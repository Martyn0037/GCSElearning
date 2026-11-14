# backend/app/practice/insights.py
"""Read models for "My mistakes", reviews due, and progress charts.

All queries are scoped to one student and use a fixed number of grouped
queries (no N+1). Lists are cursor-paginated.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import Date, Row, Select, and_, case, cast, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import Cursor
from app.models.curriculum import LearningObjective, Subject, Subtopic, Topic
from app.models.enrolment import StudentSubject
from app.models.question import Mistake, ObjectiveProgress, PracticeItem, Question
from app.practice.insight_schemas import (
    DailyActivity,
    MisconceptionCount,
    MistakeOut,
    MistakePage,
    MistakeTopicGroup,
    ObjectiveStat,
    ProgressOut,
    ReviewSummaryOut,
    TopicProgress,
)
from app.practice.mastery import P_INIT
from app.practice.review import LONDON, london_today
from app.practice.schemas import OptionOut

HISTORY_DAYS = 30
STAT_LIMIT = 3


def _mistake_select() -> Select[Mistake, Question, str, Topic, str]:
    return (
        select(Mistake, Question, LearningObjective.ref, Topic, Subject.name)
        .join(Question, Question.id == Mistake.question_id)
        .join(LearningObjective, LearningObjective.id == Mistake.objective_id)
        .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(StudentSubject, StudentSubject.id == Mistake.enrolment_id)
        .join(Subject, Subject.id == StudentSubject.subject_id)
    )


def _mistake_out(row: Row[Mistake, Question, str, Topic, str]) -> MistakeOut:
    mistake, question, objective_ref, topic, subject_name = row
    return MistakeOut(
        id=mistake.id,
        enrolment_id=mistake.enrolment_id,
        subject_name=subject_name,
        topic_id=topic.id,
        topic_ref=topic.ref,
        topic_title=topic.title,
        objective_ref=objective_ref,
        question_stem=question.stem,
        options=[OptionOut(**o) for o in question.options or []],
        student_answer=mistake.student_answer,
        correct_answer=mistake.correct_answer,
        worked_solution=question.worked_solution,
        explanation=mistake.explanation,
        explanation_status=mistake.explanation_status,
        misconception=mistake.misconception,
        assisted=mistake.assisted,
        next_review_on=None if mistake.resolved_at else mistake.next_review_on,
        resolved=mistake.resolved_at is not None,
        created_at=mistake.created_at,
    )


async def get_mistake(
    session: AsyncSession, student_id: uuid.UUID, mistake_id: uuid.UUID
) -> MistakeOut:
    """One of the student's mistakes.

    Raises:
        NotFoundError: Unknown or someone else's.
    """
    row = (
        await session.execute(
            _mistake_select().where(Mistake.id == mistake_id, Mistake.user_id == student_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Mistake not found")
    return _mistake_out(row)


async def list_mistakes(
    session: AsyncSession,
    student_id: uuid.UUID,
    *,
    resolved: bool,
    limit: int,
    cursor: Cursor | None,
) -> MistakePage:
    """Newest first, open or fixed."""
    query = _mistake_select().where(
        Mistake.user_id == student_id,
        Mistake.resolved_at.is_not(None) if resolved else Mistake.resolved_at.is_(None),
    )
    if cursor is not None:
        query = query.where(
            tuple_(Mistake.created_at, Mistake.id) < tuple_(cursor.created_at, cursor.id)
        )
    rows = (
        await session.execute(
            query.order_by(Mistake.created_at.desc(), Mistake.id.desc()).limit(limit + 1)
        )
    ).all()
    page, extra = rows[:limit], rows[limit:]
    items = [_mistake_out(r) for r in page]
    next_cursor = Cursor(items[-1].created_at, items[-1].id).encode() if extra and items else None
    return MistakePage(items=items, next_cursor=next_cursor)


async def mistake_groups(session: AsyncSession, student_id: uuid.UUID) -> list[MistakeTopicGroup]:
    """Mistakes counted by topic, then by misconception (open ones only for labels)."""
    rows = (
        await session.execute(
            select(
                StudentSubject.id,
                Subject.name,
                Topic.id,
                Topic.ref,
                Topic.title,
                Topic.position,
                Mistake.misconception,
                func.count().filter(Mistake.resolved_at.is_(None)),
                func.count().filter(Mistake.resolved_at.is_not(None)),
            )
            .select_from(Mistake)
            .join(LearningObjective, LearningObjective.id == Mistake.objective_id)
            .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(StudentSubject, StudentSubject.id == Mistake.enrolment_id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(Mistake.user_id == student_id)
            .group_by(StudentSubject.id, Subject.name, Topic.id, Mistake.misconception)
        )
    ).all()
    groups: dict[uuid.UUID, MistakeTopicGroup] = {}
    order: dict[uuid.UUID, tuple[str, int]] = {}
    for (
        enrolment_id,
        subject,
        topic_id,
        ref,
        title,
        position,
        label,
        open_count,
        fixed_count,
    ) in rows:
        group = groups.setdefault(
            topic_id,
            MistakeTopicGroup(
                enrolment_id=enrolment_id,
                subject_name=subject,
                topic_id=topic_id,
                topic_ref=ref,
                topic_title=title,
                open=0,
                fixed=0,
                misconceptions=[],
            ),
        )
        order[topic_id] = (subject, position)
        group.open += open_count
        group.fixed += fixed_count
        if open_count:
            group.misconceptions.append(
                MisconceptionCount(label=label or "other", count=open_count)
            )
    for group in groups.values():
        group.misconceptions.sort(key=lambda m: (-m.count, m.label))
    return sorted(groups.values(), key=lambda g: order[g.topic_id])


async def review_summary(
    session: AsyncSession, student_id: uuid.UUID, now: datetime
) -> ReviewSummaryOut:
    """How many mistakes are due today, and when the next one is."""
    today = london_today(now)
    due, next_due = (
        await session.execute(
            select(
                func.count().filter(Mistake.next_review_on <= today),
                func.min(Mistake.next_review_on).filter(Mistake.next_review_on > today),
            ).where(Mistake.user_id == student_id, Mistake.resolved_at.is_(None))
        )
    ).one()
    return ReviewSummaryOut(due_today=due, next_due_on=next_due)


async def progress(
    session: AsyncSession, student_id: uuid.UUID, enrolment_id: uuid.UUID, now: datetime
) -> ProgressOut:
    """Per-topic mastery and accuracy, 30 days of activity, strongest and weakest skills.

    Raises:
        NotFoundError: Unknown or someone else's subject, or one still being set up.
    """
    enrolment = await session.get(StudentSubject, enrolment_id)
    if (
        enrolment is None
        or enrolment.student_id != student_id
        or enrolment.specification_id is None
    ):
        raise NotFoundError("Subject not found")
    subject_name = await session.scalar(
        select(Subject.name).where(Subject.id == enrolment.subject_id)
    )

    rows = (
        await session.execute(
            select(Topic, LearningObjective, ObjectiveProgress)
            .join(Subtopic, Subtopic.topic_id == Topic.id)
            .join(LearningObjective, LearningObjective.subtopic_id == Subtopic.id)
            .outerjoin(
                ObjectiveProgress,
                and_(
                    ObjectiveProgress.objective_id == LearningObjective.id,
                    ObjectiveProgress.user_id == student_id,
                ),
            )
            .where(
                Topic.specification_id == enrolment.specification_id,
                Topic.retired_at.is_(None),
                LearningObjective.retired_at.is_(None),
            )
            .order_by(Topic.position, Subtopic.position, LearningObjective.position)
        )
    ).all()
    topics: dict[uuid.UUID, TopicProgress] = {}
    mastery_sums: dict[uuid.UUID, float] = defaultdict(float)
    correct_counts: dict[uuid.UUID, int] = defaultdict(int)
    stats: list[ObjectiveStat] = []
    for topic, objective, prog in rows:
        wording = objective.text_for(enrolment.tier)
        if wording is None:
            continue
        entry = topics.setdefault(
            topic.id,
            TopicProgress(
                topic_id=topic.id,
                ref=topic.ref,
                title=topic.title,
                mastery=0.0,
                objectives_total=0,
                objectives_practised=0,
                attempts=0,
                accuracy=None,
            ),
        )
        entry.objectives_total += 1
        mastery_sums[topic.id] += prog.mastery if prog else P_INIT
        if prog and prog.attempts:
            entry.objectives_practised += 1
            entry.attempts += prog.attempts
            correct_counts[topic.id] += prog.correct
            stats.append(
                ObjectiveStat(
                    ref=objective.ref, text=wording, mastery=prog.mastery, attempts=prog.attempts
                )
            )
    for topic_id, entry in topics.items():
        entry.mastery = round(mastery_sums[topic_id] / entry.objectives_total, 3)
        if entry.attempts:
            entry.accuracy = round(correct_counts[topic_id] / entry.attempts, 3)

    since = london_today(now) - timedelta(days=HISTORY_DAYS - 1)
    local_day = cast(func.timezone(LONDON.key, PracticeItem.answered_at), Date)
    daily_rows = (
        await session.execute(
            select(
                local_day,
                func.count(),
                func.sum(case((PracticeItem.correct.is_(True), 1), else_=0)),
            )
            .where(
                PracticeItem.user_id == student_id,
                PracticeItem.enrolment_id == enrolment_id,
                PracticeItem.answered_at.is_not(None),
                local_day >= since,
            )
            .group_by(local_day)
        )
    ).all()
    by_day: dict[date, tuple[int, int]] = {d: (n, int(c or 0)) for d, n, c in daily_rows}
    daily = [
        DailyActivity(
            date=day, attempts=by_day.get(day, (0, 0))[0], correct=by_day.get(day, (0, 0))[1]
        )
        for day in (since + timedelta(days=i) for i in range(HISTORY_DAYS))
    ]
    ranked = sorted(stats, key=lambda s: s.mastery)
    return ProgressOut(
        enrolment_id=enrolment.id,
        subject_name=subject_name or "",
        topics=list(topics.values()),
        daily=daily,
        strongest=list(reversed(ranked[-STAT_LIMIT:])) if ranked else [],
        weakest=ranked[:STAT_LIMIT],
    )
