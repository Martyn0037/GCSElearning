# backend/app/ai/gateway.py
"""The one place Claude is called from: budget, circuit breaker, validation retries, usage.

Every call:
1. is refused fast if the circuit is open (Claude recently failing);
2. reserves its worst-case cost (refused if over the daily/monthly cap);
3. runs, with the reply validated against a Pydantic schema plus an optional
   semantic check, retrying up to ``max_validation_retries`` times;
4. settles the actual cost and records tokens (never prompt/response text).

Callers get either a valid object or :class:`AiUnavailableError`, and fall
back to the cached question bank.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel

from app.ai.budget import BudgetExceededError, BudgetLedger
from app.ai.circuit import CircuitBreaker
from app.ai.client import Effort, LlmCallError, LlmClient
from app.ai.pricing import cost_usd, worst_case_usd
from app.core.clock import Clock
from app.core.config import Settings

logger = logging.getLogger(__name__)

# Rough upper bound for prompt size, used only for the budget reservation.
MAX_PROMPT_TOKENS = 4000


class AiUnavailableError(Exception):
    """Claude can't be used right now; serve cached content instead.

    Attributes:
        reason: ``no_api_key``, ``budget``, ``circuit_open``, ``call_failed`` or
            ``invalid_output``.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AiRequest[T: BaseModel]:
    """One structured request."""

    purpose: str
    model: str
    system: str
    user: str
    schema: type[T]
    max_tokens: int = 4000
    effort: Effort = "medium"


class AiGateway:
    """Budgeted, circuit-protected, validated access to Claude."""

    def __init__(
        self,
        client: LlmClient | None,
        ledger: BudgetLedger,
        breaker: CircuitBreaker,
        settings: Settings,
        clock: Clock,
    ) -> None:
        """Create the gateway.

        Args:
            client: The Claude client, or ``None`` when no API key is configured.
            ledger: Budget bookkeeping.
            breaker: Circuit breaker shared by this process.
            settings: Prices and retry limits.
            clock: Time source.
        """
        self._client = client
        self._ledger = ledger
        self._breaker = breaker
        self._settings = settings
        self._clock = clock

    async def structured[T: BaseModel](
        self, request: AiRequest[T], check: Callable[[T], str | None] | None = None
    ) -> T:
        """Get a schema-valid (and ``check``-passing) object from Claude.

        Args:
            request: What to ask.
            check: Extra validation; returns a problem description, or ``None``
                if the object is acceptable. Failing objects are retried.

        Returns:
            The validated object.

        Raises:
            AiUnavailableError: If Claude can't be used or never produced a
                valid answer within the retry limit.
        """
        if self._client is None:
            raise AiUnavailableError("no_api_key", "No Anthropic API key configured")
        problems: list[str] = []
        for _ in range(1 + self._settings.ai_max_validation_retries):
            result, problem = await self._attempt(self._client, request, check)
            if result is not None:
                return result
            problems.append(problem or "unknown")
        logger.warning(
            "ai_output_rejected", extra={"purpose": request.purpose, "problems": problems}
        )
        raise AiUnavailableError("invalid_output", "; ".join(problems))

    async def _attempt[T: BaseModel](
        self, client: LlmClient, request: AiRequest[T], check: Callable[[T], str | None] | None
    ) -> tuple[T | None, str | None]:
        if not await self._breaker.allow():
            raise AiUnavailableError("circuit_open", "Claude is temporarily unavailable")
        prices = self._settings.ai_prices_usd_per_mtok
        try:
            usage_id = await self._ledger.reserve(
                purpose=request.purpose,
                model=request.model,
                worst_case_usd=worst_case_usd(
                    prices, request.model, MAX_PROMPT_TOKENS, request.max_tokens
                ),
                now=self._clock.now(),
            )
        except BudgetExceededError as exc:
            raise AiUnavailableError("budget", str(exc)) from exc

        try:
            response = await client.parse(
                model=request.model,
                system=request.system,
                user=request.user,
                schema=request.schema,
                max_tokens=request.max_tokens,
                effort=request.effort,
            )
        except LlmCallError as exc:
            await self._breaker.record_failure()
            billed = cost_usd(prices, request.model, exc.usage) if exc.usage else Decimal(0)
            await self._ledger.fail(usage_id, exc.kind, exc.usage, billed)
            logger.warning("ai_call_failed", extra={"purpose": request.purpose, "kind": exc.kind})
            raise AiUnavailableError("call_failed", str(exc)) from exc

        await self._breaker.record_success()
        await self._ledger.settle(
            usage_id,
            response.usage,
            cost_usd(prices, request.model, response.usage),
            response.request_id,
        )
        if response.stop_reason == "refusal":
            return None, "model declined the request"
        if response.parsed is None:
            return None, f"no valid output (stop_reason={response.stop_reason})"
        problem = check(response.parsed) if check else None
        return (None, problem) if problem else (response.parsed, None)
