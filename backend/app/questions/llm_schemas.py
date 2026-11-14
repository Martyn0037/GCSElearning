# backend/app/questions/llm_schemas.py
"""The JSON shapes Claude must return for question generation and verification.

Kept to simple types (strings, numbers, lists, nullable fields) so they work
with structured outputs; detailed rules are enforced afterwards in
``app.questions.validation``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneratedOption(_Out):
    """A multiple-choice option."""

    label: Literal["A", "B", "C", "D"]
    text: str


class GeneratedQuestion(_Out):
    """A question with its marking key, worked solution and four hints."""

    question_type: Literal["multiple_choice", "numeric", "short_text"]
    command_word: str = Field(description="The GCSE command word the stem starts with or uses")
    stem: str = Field(description="The question text; maths in LaTeX between $...$")
    options: list[GeneratedOption] = Field(
        description="Exactly four options for multiple_choice; empty otherwise"
    )
    correct_option: str | None = Field(description="A-D for multiple_choice; null otherwise")
    numeric_answer: str | None = Field(
        description="Exact answer as a plain decimal or integer (e.g. 3.5) for numeric; "
        "null otherwise"
    )
    numeric_tolerance: str | None = Field(
        description="Accepted absolute error for numeric (0 if exact); null otherwise"
    )
    unit: str | None = Field(description="Unit of the numeric answer (e.g. cm), or null")
    check_expression: str | None = Field(
        description="For numeric: an arithmetic expression using only numbers, + - * / ^ ( ), "
        "sqrt and pi that evaluates to the answer; null if not possible"
    )
    accepted_answers: list[str] = Field(
        description="For short_text: every acceptable short answer; empty otherwise"
    )
    marks: int = Field(description="Marks available, 1 to 6")
    worked_solution: str = Field(description="Full worked solution, step by step")
    hints: list[str] = Field(
        description="Exactly 4 hints: 1 nudge, 2 strategy/first step, 3 most of the method "
        "without the final answer, 4 full worked solution"
    )


class Verification(_Out):
    """An independent check of a generated question."""

    solved_answer: str = Field(description="Your own answer, worked out before reading the key")
    answer_is_correct: bool
    within_objective: bool
    suitable_for_tier: bool
    difficulty_matches: bool
    hints_reveal_answer_early: bool
    mark_scheme_consistent: bool
    confidence: float = Field(
        description="0 to 1: how sure you are the question is correct and fair"
    )
    issues: list[str]
