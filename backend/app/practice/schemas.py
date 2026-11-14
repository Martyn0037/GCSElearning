# backend/app/practice/schemas.py
"""Request/response bodies for practice."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.core.schemas import ApiModel
from app.models.question import QuestionType
from app.questions.marking import MAX_ANSWER_LENGTH

AnswerText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ANSWER_LENGTH)
]


class OptionOut(ApiModel):
    """A multiple-choice option."""

    label: str
    text: str


class PracticeItemOut(ApiModel):
    """A question as the student sees it. Never includes the answer."""

    id: uuid.UUID
    question_type: QuestionType
    command_word: str
    stem: str
    options: list[OptionOut]
    unit: str | None
    marks: int
    difficulty: int = Field(description="1 recall ... 5 exam-style")
    objective_ref: str
    hints: list[str] = Field(description="Hints revealed so far, in order")
    hints_remaining: int
    review: bool = Field(description="True when this is a spaced review of an earlier mistake")


class AnswerRequest(ApiModel):
    """The student's answer: an option label, a number, or a short phrase."""

    answer: AnswerText


class FlagRequest(ApiModel):
    """A "this looks wrong" report."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class AnswerResultOut(ApiModel):
    """The marked answer."""

    item_id: uuid.UUID
    correct: bool
    assisted: bool
    correct_answer: str
    worked_solution: str
    level_before: int
    level_after: int
    mistake_id: uuid.UUID | None = Field(
        description="Set when this answer opened (or is reviewing) a mistake"
    )
    review: bool
    mistake_resolved: bool = Field(description="A review answered right twice in a row")
