# backend/tests/fixtures/fake_llm.py
"""A scripted stand-in for Claude, plus canned "recorded" responses.

Each call pops the next scripted reply for the requested schema; a reply can
be a model instance, ``None`` (output didn't parse), or an exception to raise.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.ai.client import Effort, LlmCallError, LlmResponse
from app.ai.pricing import TokenUsage
from app.questions.llm_schemas import GeneratedOption, GeneratedQuestion, Verification

USAGE = TokenUsage(
    input_tokens=1200, output_tokens=800, cache_read_tokens=900, cache_write_tokens=0
)


@dataclass
class Reply:
    """One scripted reply."""

    parsed: BaseModel | None = None
    stop_reason: str = "end_turn"
    error: LlmCallError | None = None


@dataclass
class FakeLlmClient:
    """Implements :class:`app.ai.client.LlmClient` from a script."""

    script: dict[type[BaseModel], deque[Reply]] = field(default_factory=lambda: defaultdict(deque))
    calls: list[dict[str, Any]] = field(default_factory=list)

    def add(self, schema: type[BaseModel], *replies: Reply) -> FakeLlmClient:
        """Queue replies for ``schema``."""
        self.script[schema].extend(replies)
        return self

    async def parse[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int,
        effort: Effort,
    ) -> LlmResponse[T]:
        """Return (or raise) the next scripted reply for ``schema``."""
        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        if not self.script[schema]:
            raise AssertionError(f"no scripted reply left for {schema.__name__}")
        reply = self.script[schema].popleft()
        if reply.error is not None:
            raise reply.error
        return LlmResponse(
            parsed=reply.parsed,  # type: ignore[arg-type]
            stop_reason=reply.stop_reason,
            usage=USAGE,
            request_id="req_test",
        )


def mcq(**overrides: Any) -> GeneratedQuestion:
    """A valid multiple-choice question (as if recorded from Claude)."""
    data: dict[str, Any] = {
        "question_type": "multiple_choice",
        "command_word": "Write down",
        "stem": "Write down the highest common factor of $12$ and $18$.",
        "options": [
            GeneratedOption(label="A", text="2"),
            GeneratedOption(label="B", text="3"),
            GeneratedOption(label="C", text="6"),
            GeneratedOption(label="D", text="36"),
        ],
        "correct_option": "C",
        "numeric_answer": None,
        "numeric_tolerance": None,
        "unit": None,
        "check_expression": None,
        "accepted_answers": [],
        "marks": 1,
        "worked_solution": (
            "Factors of 12: 1, 2, 3, 4, 6, 12. Factors of 18: 1, 2, 3, 6, 9, 18. Highest common: 6."
        ),
        "hints": [
            "What does 'highest common factor' mean?",
            "List all the factors of each number.",
            "Find the numbers that appear in both lists.",
            "Both lists contain 1, 2, 3 and 6, so the HCF is 6.",
        ],
    }
    data.update(overrides)
    return GeneratedQuestion(**data)


def numeric(**overrides: Any) -> GeneratedQuestion:
    """A valid numeric question with a check expression."""
    data: dict[str, Any] = {
        "question_type": "numeric",
        "command_word": "Work out",
        "stem": "Work out $\\frac{7}{2} + 1.25$.",
        "options": [],
        "correct_option": None,
        "numeric_answer": "4.75",
        "numeric_tolerance": "0",
        "unit": None,
        "check_expression": "7/2 + 1.25",
        "accepted_answers": [],
        "marks": 2,
        "worked_solution": "$\\frac{7}{2} = 3.5$, and $3.5 + 1.25 = 4.75$.",
        "hints": [
            "Can you write both numbers in the same form?",
            "Convert the fraction to a decimal first.",
            "$\\frac{7}{2} = 3.5$; now add 1.25.",
            "$3.5 + 1.25 = 4.75$.",
        ],
    }
    data.update(overrides)
    return GeneratedQuestion(**data)


def short_text(**overrides: Any) -> GeneratedQuestion:
    """A valid short-text question."""
    data: dict[str, Any] = {
        "question_type": "short_text",
        "command_word": "State",
        "stem": "State the name for a number with exactly two factors.",
        "options": [],
        "correct_option": None,
        "numeric_answer": None,
        "numeric_tolerance": None,
        "unit": None,
        "check_expression": None,
        "accepted_answers": ["prime", "prime number", "a prime"],
        "marks": 1,
        "worked_solution": "A number with exactly two factors (1 and itself) is a prime number.",
        "hints": [
            "Think about numbers like 2, 3, 5 and 7.",
            "How many factors do those numbers have?",
            "They have only 1 and themselves as factors.",
            "These are called prime numbers.",
        ],
    }
    data.update(overrides)
    return GeneratedQuestion(**data)


def verification(**overrides: Any) -> Verification:
    """A passing verification (override fields to make it fail)."""
    data: dict[str, Any] = {
        "solved_answer": "C",
        "answer_is_correct": True,
        "within_objective": True,
        "suitable_for_tier": True,
        "difficulty_matches": True,
        "hints_reveal_answer_early": False,
        "mark_scheme_consistent": True,
        "confidence": 0.95,
        "issues": [],
    }
    data.update(overrides)
    return Verification(**data)
