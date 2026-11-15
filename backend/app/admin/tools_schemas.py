# backend/app/admin/tools_schemas.py
"""Admin review-queue and cost-dashboard bodies."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from app.core.schemas import ApiModel
from app.models.learning import LearnCardStatus
from app.models.question import QuestionStatus, QuestionType


class FlagOut(ApiModel):
    """A student's "this looks wrong" report."""

    reason: str | None
    created_at: datetime


class ReviewQuestionOut(ApiModel):
    """A question waiting for the admin, with everything needed to judge it."""

    id: uuid.UUID
    status: QuestionStatus
    question_type: QuestionType
    difficulty: int
    objective_ref: str
    objective_text: str
    subject_name: str
    stem: str
    options: list[dict[str, str]]
    answer: dict[str, Any]
    marks: int
    worked_solution: str
    hints: list[str]
    confidence: float
    verification_notes: str | None
    flags: list[FlagOut]
    created_at: datetime


class ReviewQuestionPage(ApiModel):
    """A page of the review queue, oldest first."""

    items: list[ReviewQuestionOut]
    next_cursor: str | None


class ReviewDecision(ApiModel):
    """What to do with a reviewed question or card."""

    action: Literal["approve", "reject", "retire"]


class ReviewLearnCardOut(ApiModel):
    """A learn card waiting for review."""

    id: uuid.UUID
    status: LearnCardStatus
    objective_ref: str
    objective_text: str
    explanation: str
    worked_example: str
    created_at: datetime


class CostDayOut(ApiModel):
    """Spend on one London day."""

    date: date
    gbp: Decimal
    calls: int


class CostPurposeOut(ApiModel):
    """This month's spend for one kind of call."""

    purpose: str
    gbp: Decimal
    calls: int
    failures: int


class CostsOut(ApiModel):
    """Claude spend against the caps (pounds, converted at the configured rate)."""

    today_gbp: Decimal
    month_gbp: Decimal
    daily_cap_gbp: Decimal
    monthly_cap_gbp: Decimal
    usd_to_gbp: Decimal
    month_calls: int
    month_failures: int
    by_purpose: list[CostPurposeOut]
    last_30_days: list[CostDayOut] = Field(description="Oldest first; days without calls are 0")
    api_key_configured: bool
