# backend/app/ai/pricing.py
"""Turning token counts into money, for budgets and the cost dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

PER_MILLION = Decimal(1_000_000)
CACHE_WRITE_MULTIPLIER = Decimal("1.25")  # 5-minute cache writes
CACHE_READ_MULTIPLIER = Decimal("0.1")


class UnknownModelPriceError(Exception):
    """A model has no configured price, so its cost can't be bounded."""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Tokens billed for one call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def price_for(prices: dict[str, tuple[Decimal, Decimal]], model: str) -> tuple[Decimal, Decimal]:
    """Return (input, output) dollars per million tokens for ``model``.

    Raises:
        UnknownModelPriceError: If the model isn't in the price table. Calls
            to unpriced models are refused rather than risk an unbounded bill.
    """
    try:
        return prices[model]
    except KeyError as exc:
        raise UnknownModelPriceError(f"No price configured for model {model!r}") from exc


def cost_usd(prices: dict[str, tuple[Decimal, Decimal]], model: str, usage: TokenUsage) -> Decimal:
    """Dollar cost of a call from its token usage.

    ``input_tokens`` excludes cached tokens (as the API reports it), so cache
    reads and writes are priced separately on top.
    """
    input_price, output_price = price_for(prices, model)
    total = (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.cache_write_tokens) * input_price * CACHE_WRITE_MULTIPLIER
        + Decimal(usage.cache_read_tokens) * input_price * CACHE_READ_MULTIPLIER
        + Decimal(usage.output_tokens) * output_price
    )
    return (total / PER_MILLION).quantize(Decimal("0.000001"))


def worst_case_usd(
    prices: dict[str, tuple[Decimal, Decimal]],
    model: str,
    max_input_tokens: int,
    max_output_tokens: int,
) -> Decimal:
    """Upper bound on a call's cost, reserved against the budget before it runs.

    Assumes every input token is a (most expensive) cache write and the full
    ``max_tokens`` is produced.
    """
    return cost_usd(
        prices,
        model,
        TokenUsage(cache_write_tokens=max_input_tokens, output_tokens=max_output_tokens),
    )
