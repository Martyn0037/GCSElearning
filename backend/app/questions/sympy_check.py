# backend/app/questions/sympy_check.py
"""Independently re-compute a numeric answer from the model's check expression.

The expression comes from Claude, so it is treated as untrusted:
1. it must match a strict allowlist (digits, + - * / ^ ( ), sqrt, pi, spaces);
2. it is evaluated in a separate, isolated Python process with a hard timeout,
   so a pathological expression (e.g. 9^9^9^9) can't hang or exhaust the API.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from enum import StrEnum
from fractions import Fraction

logger = logging.getLogger(__name__)

MAX_EXPRESSION_LENGTH = 200
EVAL_TIMEOUT_SECONDS = 5.0

# Whole-expression allowlist: numbers, operators, brackets, sqrt and pi only.
_ALLOWED = re.compile(r"^(?:[0-9.\s+\-*/^()]|sqrt|pi)+$")

# Run with -I (isolated: no user site, no cwd on sys.path) so nothing local is imported.
_EVALUATOR = """
import sys
from sympy import N, pi, sqrt, sympify
expr = sys.stdin.read()
value = sympify(expr.replace("^", "**"), locals={"sqrt": sqrt, "pi": pi}, rational=True)
print(N(value, 30))
"""


class CheckOutcome(StrEnum):
    """Result of the independent numeric check."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNCHECKED = "unchecked"  # no usable expression, or it couldn't be evaluated


def is_safe_expression(expression: str) -> bool:
    """Whether the expression is within the allowlist and length limit."""
    return 0 < len(expression) <= MAX_EXPRESSION_LENGTH and bool(_ALLOWED.match(expression))


async def evaluate(expression: str) -> Fraction | None:
    """Evaluate an allowlisted expression in an isolated subprocess.

    Returns:
        The value (to 30 significant figures), or ``None`` if it failed or timed out.
    """
    if not is_safe_expression(expression):
        return None
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        _EVALUATOR,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(expression.encode()), timeout=EVAL_TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        logger.info("sympy_check_timeout")
        return None
    if process.returncode != 0:
        return None
    try:
        return Fraction(stdout.decode().strip())
    except ValueError:
        return None


async def check_numeric_answer(
    expression: str | None, expected: Fraction, tolerance: Fraction
) -> CheckOutcome:
    """Compare the expression's value with the stated answer.

    A value within ``max(tolerance, 1e-9 relative)`` counts as a match, so
    exact answers aren't failed by rounding in the 30-digit evaluation.
    """
    if not expression:
        return CheckOutcome.UNCHECKED
    value = await evaluate(expression)
    if value is None:
        return CheckOutcome.UNCHECKED
    slack = max(tolerance, abs(expected) * Fraction(1, 10**9), Fraction(1, 10**12))
    return CheckOutcome.MATCH if abs(value - expected) <= slack else CheckOutcome.MISMATCH
