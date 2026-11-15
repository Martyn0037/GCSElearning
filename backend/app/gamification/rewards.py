# backend/app/gamification/rewards.py
"""Awarding XP, counting streak days and granting badges.

Every write is safe to repeat: XP events and badges are unique per student
and source, so retries and races never pay out twice. Methods don't commit;
they run inside the caller's unit of work (e.g. marking an answer).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification import badges as badge_rules
from app.gamification.schemas import BadgeOut
from app.gamification.streaks import StreakState, StreakUpdate, record_activity
from app.models.gamification import (
    Challenge,
    ChallengeKind,
    ChallengeStatus,
    Streak,
    UserBadge,
    XpEvent,
    XpSource,
)
from app.models.question import Mistake, PracticeItem
from app.practice.review import london_today


class Rewards:
    """XP, streak and badge writes for one request."""

    def __init__(self, session: AsyncSession, now: datetime) -> None:
        """Create the helper.

        Args:
            session: The caller's session (not committed here).
            now: Request time.
        """
        self._session = session
        self._now = now

    async def total_xp(self, user_id: uuid.UUID) -> int:
        """All XP the student has earned."""
        total = await self._session.scalar(
            select(func.coalesce(func.sum(XpEvent.amount), 0)).where(XpEvent.user_id == user_id)
        )
        return int(total or 0)

    async def award(
        self, user_id: uuid.UUID, source: XpSource, ref_id: uuid.UUID, amount: int
    ) -> int:
        """Award XP once per (source, ref). Returns the XP actually added (0 if repeated)."""
        if amount <= 0:
            return 0
        added = await self._session.scalar(
            insert(XpEvent)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                source=source,
                ref_id=ref_id,
                amount=amount,
                created_at=self._now,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "source", "ref_id"])
            .returning(XpEvent.amount)
        )
        return int(added or 0)

    async def record_activity(self, user_id: uuid.UUID) -> StreakUpdate:
        """Count today (London) towards the streak. Locks the streak row."""
        await self._session.execute(
            insert(Streak)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        row = await self._session.get(Streak, user_id, with_for_update=True, populate_existing=True)
        assert row is not None  # noqa: S101 - inserted above
        update = record_activity(
            StreakState(
                row.current_days, row.longest_days, row.last_active_on, row.freeze_used_week
            ),
            london_today(self._now),
        )
        if update.extended:
            row.current_days = update.state.current
            row.longest_days = update.state.longest
            row.last_active_on = update.state.last_active_on
            row.freeze_used_week = update.state.freeze_used_week
            row.updated_at = self._now
        return update

    async def grant_badges(
        self, user_id: uuid.UUID, *, exam_ready_topic: bool = False
    ) -> list[BadgeOut]:
        """Grant any newly earned badges and return them (in catalogue order)."""
        have = set(
            (
                await self._session.scalars(
                    select(UserBadge.badge_code).where(UserBadge.user_id == user_id)
                )
            ).all()
        )
        if len(have) == len(badge_rules.CATALOGUE):
            return []
        qualified = badge_rules.earned(await self._stats(user_id, exam_ready_topic))
        new_codes = [b.code for b in badge_rules.CATALOGUE if b.code in qualified - have]
        granted: list[BadgeOut] = []
        for code in new_codes:
            inserted = await self._session.scalar(
                insert(UserBadge)
                .values(user_id=user_id, badge_code=code, awarded_at=self._now)
                .on_conflict_do_nothing(index_elements=["user_id", "badge_code"])
                .returning(UserBadge.badge_code)
            )
            if inserted:
                badge = badge_rules.BY_CODE[code]
                granted.append(
                    BadgeOut(
                        code=code,
                        name=badge.name,
                        description=badge.description,
                        earned_at=self._now,
                    )
                )
        return granted

    async def _stats(self, user_id: uuid.UUID, exam_ready_topic: bool) -> badge_rules.BadgeStats:
        """Everything the badge rules need, in one round trip."""
        answered = PracticeItem.answered_at.is_not(None)
        row = (
            await self._session.execute(
                select(
                    select(func.count())
                    .select_from(Mistake)
                    .where(Mistake.user_id == user_id, Mistake.resolved_at.is_not(None))
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(PracticeItem)
                    .where(PracticeItem.user_id == user_id, answered)
                    .scalar_subquery(),
                    exists().where(
                        PracticeItem.user_id == user_id,
                        answered,
                        PracticeItem.correct.is_(True),
                        PracticeItem.hints_revealed == 0,
                        PracticeItem.difficulty == 5,
                    ),
                    select(Streak.longest_days).where(Streak.user_id == user_id).scalar_subquery(),
                    select(func.count())
                    .select_from(Challenge)
                    .where(
                        Challenge.user_id == user_id,
                        Challenge.kind == ChallengeKind.DAILY,
                        Challenge.status == ChallengeStatus.COMPLETED,
                    )
                    .scalar_subquery(),
                    select(func.max(Challenge.percent))
                    .where(
                        Challenge.user_id == user_id,
                        Challenge.kind == ChallengeKind.BOSS,
                        Challenge.status == ChallengeStatus.COMPLETED,
                    )
                    .scalar_subquery(),
                )
            )
        ).one()
        fixed, count, exam_style, longest, daily, best_boss = row
        return badge_rules.BadgeStats(
            fixed=fixed,
            answered=count,
            exam_style_unaided=bool(exam_style),
            longest_streak=longest or 0,
            daily_completed=daily,
            best_boss_percent=best_boss,
            exam_ready_topic=exam_ready_topic,
        )
