# backend/app/jobs/handlers.py
"""What each background job kind does."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import AiUnavailableError
from app.auth import rate_limit
from app.core.clock import Clock
from app.core.config import Settings
from app.models.curriculum import Tier
from app.questions.bank import GENERATE_JOB, plan_top_up
from app.questions.generator import ObjectiveNotAvailableError, QuestionGenerator

logger = logging.getLogger(__name__)

TOP_UP_JOB = "top_up_bank"
PURGE_RATE_LIMITS_JOB = "purge_rate_limits"


class RetryLaterError(Exception):
    """The job couldn't run now but may succeed later (queue retries with backoff)."""


@dataclass(frozen=True, slots=True)
class JobContext:
    """Shared dependencies for handlers."""

    session_factory: async_sessionmaker[AsyncSession]
    generator: QuestionGenerator
    settings: Settings
    clock: Clock


Handler = Callable[[JobContext, dict[str, Any]], Awaitable[None]]


async def generate_question(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Generate one question. Skips quietly when Claude isn't configured or the budget is spent.

    Raises:
        RetryLaterError: On a transient Claude failure (outage, invalid output).
    """
    tier = Tier(payload["tier"]) if payload.get("tier") else None
    try:
        await ctx.generator.generate(
            uuid.UUID(payload["objective_id"]), tier, int(payload["difficulty"])
        )
    except ObjectiveNotAvailableError:
        logger.info("generation_skipped_objective_unavailable")
    except AiUnavailableError as exc:
        if exc.reason in {"no_api_key", "budget"}:
            # Not going to change soon; the next top-up will re-queue it.
            logger.info("generation_skipped", extra={"reason": exc.reason})
            return
        raise RetryLaterError(f"{exc.reason}: {exc}") from exc


async def top_up_bank(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Queue generation wherever a student is running low on unseen questions."""
    async with ctx.session_factory() as session:
        queued = await plan_top_up(session, ctx.clock.now(), ctx.settings.question_bank_target)
    logger.info("bank_top_up", extra={"queued": queued})


async def purge_rate_limits(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Delete rate-limit counters older than a day."""
    async with ctx.session_factory() as session:
        deleted = await rate_limit.purge_expired(session, ctx.clock.now() - timedelta(days=1))
    logger.info("rate_limits_purged", extra={"deleted": deleted})


HANDLERS: dict[str, Handler] = {
    GENERATE_JOB: generate_question,
    TOP_UP_JOB: top_up_bank,
    PURGE_RATE_LIMITS_JOB: purge_rate_limits,
}
