# backend/app/ai/budget.py
"""Daily and monthly spending caps, enforced before every Claude call.

Reserve-then-settle: a call first reserves its worst-case cost inside a
transaction holding a Postgres advisory lock, so concurrent calls can't both
squeeze under the cap. When it finishes, the reservation is replaced by the
actual cost. Days and months are counted in Europe/London time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.pricing import TokenUsage
from app.models.ops import AiUsage, UsageStatus

LONDON = ZoneInfo("Europe/London")
# Arbitrary constant naming the budget lock (pg_advisory_xact_lock key).
_BUDGET_LOCK_KEY = 0x6C6C6D_62756467


class BudgetExceededError(Exception):
    """This call would take spending past the daily or monthly cap."""


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Caps in dollars (converted from the configured pounds)."""

    daily_usd: Decimal
    monthly_usd: Decimal


@dataclass(frozen=True, slots=True)
class Spend:
    """Spending so far, counting in-flight reservations at their worst case."""

    today_usd: Decimal
    month_usd: Decimal


def period_starts(now: datetime) -> tuple[datetime, datetime]:
    """Start of the current London day and month, as aware datetimes."""
    local = now.astimezone(LONDON)
    day = datetime.combine(local.date(), time.min, tzinfo=LONDON)
    month = day.replace(day=1)
    return day, month


async def current_spend(session: AsyncSession, now: datetime) -> Spend:
    """Sum settled costs and open reservations for today and this month.

    A reservation counts at its worst case until settled, so concurrent
    in-flight calls are included.
    """
    day_start, month_start = period_starts(now)
    held = func.coalesce(
        func.sum(
            case(
                (AiUsage.status == UsageStatus.RESERVED, AiUsage.reserved_usd),
                else_=AiUsage.cost_usd,
            )
        ),
        0,
    )
    today = await session.scalar(select(held).where(AiUsage.created_at >= day_start))
    month = await session.scalar(select(held).where(AiUsage.created_at >= month_start))
    return Spend(today_usd=Decimal(today or 0), month_usd=Decimal(month or 0))


class BudgetLedger:
    """Reserves and settles Claude spending. Each method uses its own short transaction."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], limits: BudgetLimits
    ) -> None:
        """Create a ledger.

        Args:
            session_factory: Opens short, independent transactions (budget
                bookkeeping must commit even if the caller's work rolls back).
            limits: The caps.
        """
        self._sessions = session_factory
        self._limits = limits

    async def reserve(
        self, *, purpose: str, model: str, worst_case_usd: Decimal, now: datetime
    ) -> uuid.UUID:
        """Hold ``worst_case_usd`` against today's and this month's caps.

        Returns:
            The usage row ID, to pass to :meth:`settle` or :meth:`fail`.

        Raises:
            BudgetExceededError: If the hold would exceed either cap.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BUDGET_LOCK_KEY})
            spend = await current_spend(session, now)
            if spend.today_usd + worst_case_usd > self._limits.daily_usd:
                raise BudgetExceededError("daily AI budget reached")
            if spend.month_usd + worst_case_usd > self._limits.monthly_usd:
                raise BudgetExceededError("monthly AI budget reached")
            row = AiUsage(
                id=uuid.uuid4(),
                created_at=now,
                purpose=purpose,
                model=model,
                status=UsageStatus.RESERVED,
                reserved_usd=worst_case_usd,
            )
            session.add(row)
            return row.id

    async def settle(
        self, usage_id: uuid.UUID, usage: TokenUsage, cost: Decimal, request_id: str | None
    ) -> None:
        """Replace the reservation with the actual cost."""
        await self._finish(usage_id, UsageStatus.SETTLED, usage, cost, request_id, None)

    async def fail(
        self,
        usage_id: uuid.UUID,
        error_type: str,
        usage: TokenUsage | None = None,
        cost: Decimal = Decimal(0),
    ) -> None:
        """Release the reservation of a call that failed (charging anything billed)."""
        await self._finish(
            usage_id, UsageStatus.FAILED, usage or TokenUsage(), cost, None, error_type
        )

    async def _finish(
        self,
        usage_id: uuid.UUID,
        status: UsageStatus,
        usage: TokenUsage,
        cost: Decimal,
        request_id: str | None,
        error_type: str | None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            row = await session.get(AiUsage, usage_id, with_for_update=True)
            if row is None:  # pragma: no cover - reserve() always creates it
                return
            row.status = status
            row.cost_usd = cost
            row.input_tokens = usage.input_tokens
            row.output_tokens = usage.output_tokens
            row.cache_read_tokens = usage.cache_read_tokens
            row.cache_write_tokens = usage.cache_write_tokens
            row.request_id = request_id
            row.error_type = error_type
