# backend/app/admin/tools.py
"""Admin review queue (strict mode, flagged questions, learn cards) and cost dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.tools_schemas import (
    CostDayOut,
    CostPurposeOut,
    CostsOut,
    FlagOut,
    ReviewLearnCardOut,
    ReviewQuestionOut,
    ReviewQuestionPage,
)
from app.ai.budget import period_starts
from app.auth import audit
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Cursor
from app.models.curriculum import LearningObjective, Specification, Subject
from app.models.learning import LearnCard, LearnCardStatus
from app.models.ops import AiUsage, UsageStatus
from app.models.question import Hint, Question, QuestionFlag, QuestionStatus
from app.practice.review import LONDON, london_today

REVIEWABLE = (QuestionStatus.PENDING_REVIEW, QuestionStatus.FLAGGED)
NEW_STATUS = {
    "approve": QuestionStatus.ACTIVE,
    "reject": QuestionStatus.REJECTED,
    "retire": QuestionStatus.RETIRED,
}


async def review_queue(
    session: AsyncSession, *, status: QuestionStatus | None, limit: int, cursor: Cursor | None
) -> ReviewQuestionPage:
    """Questions waiting for review (pending and/or flagged), oldest first."""
    statuses = (status,) if status else REVIEWABLE
    query = (
        select(Question, LearningObjective, Subject.name)
        .join(LearningObjective, LearningObjective.id == Question.objective_id)
        .join(Specification, Specification.id == LearningObjective.specification_id)
        .join(Subject, Subject.id == Specification.subject_id)
        .where(Question.status.in_(statuses))
        .order_by(Question.created_at, Question.id)
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(
            or_(
                Question.created_at > cursor.created_at,
                and_(Question.created_at == cursor.created_at, Question.id > cursor.id),
            )
        )
    rows = (await session.execute(query)).all()
    page = rows[:limit]
    ids = [q.id for q, _, _ in page]
    hints: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    for qid, text in (
        await session.execute(
            select(Hint.question_id, Hint.text)
            .where(Hint.question_id.in_(ids))
            .order_by(Hint.level)
        )
    ).all():
        hints[qid].append(text)
    flags: dict[uuid.UUID, list[FlagOut]] = {i: [] for i in ids}
    for flag in (
        await session.scalars(
            select(QuestionFlag)
            .where(QuestionFlag.question_id.in_(ids), QuestionFlag.resolved_at.is_(None))
            .order_by(QuestionFlag.created_at)
        )
    ).all():
        flags[flag.question_id].append(FlagOut(reason=flag.reason, created_at=flag.created_at))
    items = [
        ReviewQuestionOut(
            id=q.id,
            status=q.status,
            question_type=q.question_type,
            difficulty=q.difficulty,
            objective_ref=objective.ref,
            objective_text=objective.text_for(q.tier) or objective.foundation_text or "",
            subject_name=subject,
            stem=q.stem,
            options=q.options or [],
            answer=q.answer,
            marks=q.marks,
            worked_solution=q.worked_solution,
            hints=hints[q.id],
            confidence=q.confidence,
            verification_notes=q.verification_notes,
            flags=flags[q.id],
            created_at=q.created_at,
        )
        for q, objective, subject in page
    ]
    next_cursor = (
        Cursor(created_at=page[-1][0].created_at, id=page[-1][0].id).encode()
        if len(rows) > limit
        else None
    )
    return ReviewQuestionPage(items=items, next_cursor=next_cursor)


async def decide_question(
    session: AsyncSession, admin_id: uuid.UUID, question_id: uuid.UUID, action: str, now: datetime
) -> None:
    """Approve, reject or retire a question under review; resolves its flags.

    Raises:
        NotFoundError: Unknown question.
        ConflictError: ``NOT_UNDER_REVIEW`` if it isn't pending or flagged.
    """
    question = await session.get(Question, question_id, with_for_update=True)
    if question is None:
        raise NotFoundError("Question not found")
    if question.status not in REVIEWABLE:
        raise ConflictError("This question isn't waiting for review.", code="NOT_UNDER_REVIEW")
    previous = question.status
    question.status = NEW_STATUS[action]
    for flag in (
        await session.scalars(
            select(QuestionFlag).where(
                QuestionFlag.question_id == question_id, QuestionFlag.resolved_at.is_(None)
            )
        )
    ).all():
        flag.resolved_at = now
    audit.record(
        session,
        action=f"question.{action}",
        now=now,
        actor_user_id=admin_id,
        details={"question_id": str(question_id), "from": previous.value},
    )
    await session.commit()


async def learn_card_queue(session: AsyncSession) -> list[ReviewLearnCardOut]:
    """Learn cards waiting for review (bounded: one per objective and tier)."""
    rows = (
        await session.execute(
            select(LearnCard, LearningObjective)
            .join(LearningObjective, LearningObjective.id == LearnCard.objective_id)
            .where(LearnCard.status == LearnCardStatus.PENDING_REVIEW)
            .order_by(LearnCard.created_at)
            .limit(200)
        )
    ).all()
    return [
        ReviewLearnCardOut(
            id=card.id,
            status=card.status,
            objective_ref=objective.ref,
            objective_text=objective.text_for(card.tier) or objective.foundation_text or "",
            explanation=card.explanation,
            worked_example=card.worked_example,
            created_at=card.created_at,
        )
        for card, objective in rows
    ]


async def decide_learn_card(
    session: AsyncSession, admin_id: uuid.UUID, card_id: uuid.UUID, action: str, now: datetime
) -> None:
    """Approve or reject a learn card. Rejecting deletes it so a new one can be written.

    Raises:
        NotFoundError: Unknown card.
        ConflictError: ``NOT_UNDER_REVIEW`` if it isn't pending.
    """
    card = await session.get(LearnCard, card_id, with_for_update=True)
    if card is None:
        raise NotFoundError("Learn card not found")
    if card.status is not LearnCardStatus.PENDING_REVIEW:
        raise ConflictError("This card isn't waiting for review.", code="NOT_UNDER_REVIEW")
    if action == "approve":
        card.status = LearnCardStatus.ACTIVE
    else:
        await session.delete(card)
    audit.record(
        session,
        action=f"learn_card.{action}",
        now=now,
        actor_user_id=admin_id,
        details={"objective_id": str(card.objective_id)},
    )
    await session.commit()


async def costs(session: AsyncSession, settings: Settings, now: datetime) -> CostsOut:
    """Spend today and this month (London), by purpose and day, against the caps."""
    rate = Decimal(str(settings.usd_to_gbp))
    day_start, month_start = period_starts(now)
    counted = AiUsage.status != UsageStatus.RESERVED
    spend = func.coalesce(
        func.sum(case((counted, AiUsage.cost_usd), else_=AiUsage.reserved_usd)), 0
    )
    today, month, calls, failures = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(case((AiUsage.created_at >= day_start, AiUsage.cost_usd), else_=0)), 0
                ),
                spend,
                func.count(),
                func.count(case((AiUsage.status == UsageStatus.FAILED, 1))),
            ).where(AiUsage.created_at >= month_start)
        )
    ).one()
    purposes = (
        await session.execute(
            select(
                AiUsage.purpose,
                func.coalesce(func.sum(AiUsage.cost_usd), 0),
                func.count(),
                func.count(case((AiUsage.status == UsageStatus.FAILED, 1))),
            )
            .where(AiUsage.created_at >= month_start)
            .group_by(AiUsage.purpose)
            .order_by(func.sum(AiUsage.cost_usd).desc())
        )
    ).all()
    since = london_today(now) - timedelta(days=29)
    local_day = cast(func.timezone(LONDON.key, AiUsage.created_at), Date)
    by_day = {
        day: (Decimal(str(usd)), n)
        for day, usd, n in (
            await session.execute(
                select(local_day, func.coalesce(func.sum(AiUsage.cost_usd), 0), func.count())
                .where(local_day >= since)
                .group_by(local_day)
            )
        ).all()
    }
    days = [since + timedelta(days=i) for i in range(30)]

    def gbp(usd: Decimal | float | int) -> Decimal:
        return (Decimal(str(usd)) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return CostsOut(
        today_gbp=gbp(today),
        month_gbp=gbp(month),
        daily_cap_gbp=Decimal(str(settings.ai_daily_budget_gbp)),
        monthly_cap_gbp=Decimal(str(settings.ai_monthly_budget_gbp)),
        usd_to_gbp=rate,
        month_calls=calls,
        month_failures=failures,
        by_purpose=[
            CostPurposeOut(purpose=p, gbp=gbp(usd), calls=n, failures=f)
            for p, usd, n, f in purposes
        ],
        last_30_days=[
            CostDayOut(
                date=d, gbp=gbp(by_day.get(d, (Decimal(0), 0))[0]), calls=by_day.get(d, (0, 0))[1]
            )
            for d in days
        ],
        api_key_configured=settings.anthropic_api_key is not None,
    )
