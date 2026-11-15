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
from app.learning.learn import LEARN_JOB, LearnCardWriter
from app.models.curriculum import Tier
from app.practice.explain import MistakeExplainer
from app.practice.service import EXPLAIN_JOB
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
    explainer: MistakeExplainer
    settings: Settings
    clock: Clock
    learn_writer: LearnCardWriter | None = None


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
    """Queue generation wherever a student is running low on unseen questions.

    Does nothing without an API key: the jobs could only be skipped.
    """
    if ctx.settings.anthropic_api_key is None:
        logger.info("bank_top_up_skipped", extra={"reason": "no_api_key"})
        return
    async with ctx.session_factory() as session:
        queued = await plan_top_up(session, ctx.clock.now(), ctx.settings.question_bank_target)
    logger.info("bank_top_up", extra={"queued": queued})


async def purge_rate_limits(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Delete rate-limit counters older than a day."""
    async with ctx.session_factory() as session:
        deleted = await rate_limit.purge_expired(session, ctx.clock.now() - timedelta(days=1))
    logger.info("rate_limits_purged", extra={"deleted": deleted})


async def explain_mistake(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Write the "where it went wrong" explanation (or mark it unavailable)."""
    status = await ctx.explainer.explain(uuid.UUID(payload["mistake_id"]))
    logger.info("mistake_explained", extra={"status": status.value})


async def generate_learn_card(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Write one learn card. Skips quietly without Claude or budget.

    Raises:
        RetryLaterError: On a transient Claude failure (outage, invalid output).
    """
    if ctx.learn_writer is None:
        logger.info("learn_card_skipped", extra={"reason": "no_writer"})
        return
    tier = Tier(payload["tier"]) if payload.get("tier") else None
    try:
        await ctx.learn_writer.write(uuid.UUID(payload["objective_id"]), tier)
    except ObjectiveNotAvailableError:
        logger.info("learn_card_skipped_objective_unavailable")
    except AiUnavailableError as exc:
        if exc.reason in {"no_api_key", "budget"}:
            logger.info("learn_card_skipped", extra={"reason": exc.reason})
            return
        raise RetryLaterError(f"{exc.reason}: {exc}") from exc


HANDLERS: dict[str, Handler] = {
    LEARN_JOB: generate_learn_card,
    EXPLAIN_JOB: explain_mistake,
    GENERATE_JOB: generate_question,
    TOP_UP_JOB: top_up_bank,
    PURGE_RATE_LIMITS_JOB: purge_rate_limits,
}
