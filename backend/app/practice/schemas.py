# backend/app/practice/schemas.py
"""Request/response bodies for practice."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.core.schemas import ApiModel
from app.gamification.schemas import ChallengeProgressOut, RewardsOut
from app.models.question import QuestionType
from app.practice.extended import MAX_EXTENDED_ANSWER

# Written (extended) answers can be long; other types are limited to
# MAX_ANSWER_LENGTH in the service.
AnswerText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_EXTENDED_ANSWER)
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
    keypad: bool = Field(
        description="The answer is maths: the on-screen keys replace the phone keyboard"
    )
    symbol_keys: list[str] = Field(
        description="Symbol keys to offer with the number keys (every short answer gets all)"
    )


class AnswerRequest(ApiModel):
    """The student's answer: an option label, a number, or a short phrase."""

    answer: AnswerText


class FlagRequest(ApiModel):
    """A "this looks wrong" report."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class MarkPointOut(ApiModel):
    """One marking point, and whether the answer earned it."""

    text: str
    marks: int
    ao: str
    awarded: bool


class LevelOut(ApiModel):
    """One level of a levels-based mark scheme."""

    level: int
    min_marks: int
    max_marks: int
    descriptor: str


class ExtendedMarkingOut(ApiModel):
    """How an extended answer was marked (marks are null if it couldn't be marked)."""

    marks: int | None
    marks_available: int
    level: int | None
    levels: list[LevelOut]
    points: list[MarkPointOut]
    strengths: str | None
    improvements: str | None


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
    # Optional so answers stored before Phase 5 still replay.
    rewards: RewardsOut | None = Field(default=None, description="XP, streak and badges")
    challenge: ChallengeProgressOut | None = Field(
        default=None, description="Set when the question is part of a challenge"
    )
    marked: bool = Field(
        default=True, description="False when an extended answer couldn't be marked right now"
    )
    marking: ExtendedMarkingOut | None = Field(
        default=None, description="Extended answers: marks, points earned and feedback"
    )
