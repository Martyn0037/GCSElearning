# backend/app/ai/factory.py
"""Builds the Claude client, gateway and question generator from settings."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.budget import BudgetLedger, BudgetLimits
from app.ai.circuit import CircuitBreaker
from app.ai.client import AnthropicLlmClient, LlmClient
from app.ai.gateway import AiGateway
from app.core.clock import Clock
from app.core.config import Settings
from app.questions.generator import QuestionGenerator


def build_llm_client(settings: Settings) -> LlmClient | None:
    """The real client, or ``None`` when no API key is configured (bank-only mode)."""
    if settings.anthropic_api_key is None:
        return None
    return AnthropicLlmClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout_seconds=settings.ai_timeout_seconds,
    )


def build_breaker(settings: Settings, clock: Clock) -> CircuitBreaker:
    """One breaker per process."""
    return CircuitBreaker(
        clock, settings.ai_circuit_failure_threshold, settings.ai_circuit_reset_seconds
    )


def budget_limits(settings: Settings) -> BudgetLimits:
    """Convert the pound caps to dollars (Claude bills in dollars)."""
    return BudgetLimits(
        daily_usd=settings.ai_daily_budget_gbp / settings.usd_to_gbp,
        monthly_usd=settings.ai_monthly_budget_gbp / settings.usd_to_gbp,
    )


def build_generator(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    client: LlmClient | None,
    breaker: CircuitBreaker,
    clock: Clock,
) -> QuestionGenerator:
    """Wire a generator with its budgeted, circuit-protected gateway."""
    gateway = AiGateway(
        client, BudgetLedger(session_factory, budget_limits(settings)), breaker, settings, clock
    )
    return QuestionGenerator(session_factory, gateway, settings)
