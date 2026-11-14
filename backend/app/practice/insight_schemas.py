# backend/app/practice/insight_schemas.py
"""Response bodies for mistakes, reviews and progress."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.schemas import ApiModel
from app.models.question import ExplanationStatus
from app.practice.schemas import OptionOut


class MistakeOut(ApiModel):
    """A mistake as the student sees it on "My mistakes"."""

    id: uuid.UUID
    enrolment_id: uuid.UUID
    subject_name: str
    topic_id: uuid.UUID
    topic_ref: str
    topic_title: str
    objective_ref: str
    question_stem: str
    options: list[OptionOut]
    student_answer: str
    correct_answer: str
    worked_solution: str
    explanation: str | None
    explanation_status: ExplanationStatus
    misconception: str | None
    assisted: bool
    next_review_on: date | None = Field(description="Null once fixed")
    resolved: bool
    created_at: datetime


class MistakePage(ApiModel):
    """A page of mistakes, newest first."""

    items: list[MistakeOut]
    next_cursor: str | None


class MisconceptionCount(ApiModel):
    """Open mistakes with one misconception label."""

    label: str
    count: int


class MistakeTopicGroup(ApiModel):
    """Mistake counts for one topic."""

    enrolment_id: uuid.UUID
    subject_name: str
    topic_id: uuid.UUID
    topic_ref: str
    topic_title: str
    open: int
    fixed: int
    misconceptions: list[MisconceptionCount]


class ReviewSummaryOut(ApiModel):
    """Reviews due."""

    due_today: int
    next_due_on: date | None


class TopicProgress(ApiModel):
    """Mastery and accuracy for one topic."""

    topic_id: uuid.UUID
    ref: str
    title: str
    mastery: float = Field(description="Average BKT mastery over the topic's skills, 0-1")
    objectives_total: int
    objectives_practised: int
    attempts: int
    accuracy: float | None = Field(description="Share answered correctly, or null if none yet")


class DailyActivity(ApiModel):
    """Answers on one London calendar day."""

    date: date
    attempts: int
    correct: int


class ObjectiveStat(ApiModel):
    """A practised skill with its mastery."""

    ref: str
    text: str
    mastery: float
    attempts: int


class ProgressOut(ApiModel):
    """Everything the progress page charts for one subject."""

    enrolment_id: uuid.UUID
    subject_name: str
    topics: list[TopicProgress]
    daily: list[DailyActivity]
    strongest: list[ObjectiveStat]
    weakest: list[ObjectiveStat]
