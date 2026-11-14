# backend/app/models/question.py
"""The question bank, practice items, per-objective progress and flags."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.curriculum import TIER_ENUM, Tier


class QuestionType(StrEnum):
    """How a question is answered and marked."""

    MULTIPLE_CHOICE = "multiple_choice"
    NUMERIC = "numeric"
    SHORT_TEXT = "short_text"


class QuestionStatus(StrEnum):
    """Lifecycle of a bank question. Only ``active`` questions are served."""

    PENDING_REVIEW = "pending_review"  # strict mode: waiting for the admin
    ACTIVE = "active"
    FLAGGED = "flagged"  # reported by the student; hidden until reviewed
    REJECTED = "rejected"  # failed verification; kept for the eval report
    RETIRED = "retired"


class Difficulty(IntEnum):
    """The five-level ladder (brief section 5)."""

    RECALL = 1
    UNDERSTAND = 2
    APPLY = 3
    ANALYSE = 4
    EXAM_STYLE = 5


def _enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda e: [m.value for m in e])


class Question(TimestampMixin, Base):
    """One generated, checked question for one learning objective and difficulty.

    ``answer`` holds the marking key, by type:

    - multiple_choice: ``{"correct_option": "B"}``
    - numeric: ``{"value": "3.5", "tolerance": "0.01", "unit": "cm" | null}``
    - short_text: ``{"accepted": ["prime", "a prime number"]}``
    """

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        UniqueConstraint("objective_id", "content_hash"),
        # The serving query: active questions for an objective at a level.
        Index("ix_questions_serving", "objective_id", "tier", "difficulty", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_objectives.id", ondelete="RESTRICT"), nullable=False
    )
    tier: Mapped[Tier | None] = mapped_column(TIER_ENUM)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        _enum(QuestionType, "question_type"), nullable=False
    )
    command_word: Mapped[str] = mapped_column(String(40), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB)
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    marks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    worked_solution: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(
        _enum(QuestionStatus, "question_status"), nullable=False
    )
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verification_notes: Mapped[str | None] = mapped_column(Text)
    sympy_checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    generator_model: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class Hint(Base):
    """One rung of a question's hint ladder (1 nudge ... 4 full solution)."""

    __tablename__ = "hints"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 4", name="level_range"),)

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class PracticeItem(Base):
    """A question served to a student, and their answer once given.

    Serving creates the row; answering fills in the result. The answer is
    accepted once: the same ``idempotency_key`` replays the stored result, so a
    retry or double tap never double-counts.
    """

    __tablename__ = "practice_items"
    __table_args__ = (
        Index("ix_practice_items_user_served", "user_id", "served_at"),
        Index("ix_practice_items_user_question", "user_id", "question_id"),
        Index(
            "ix_practice_items_open",
            "user_id",
            "enrolment_id",
            postgresql_where=text("answered_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    enrolment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hints_revealed: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    assisted: Mapped[bool | None] = mapped_column(Boolean)


class ObjectiveProgress(Base):
    """Where a student is on one objective's difficulty ladder."""

    __tablename__ = "objective_progress"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 5", name="level_range"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_objectives.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    # Outcomes at the current level, newest last (at most 5 kept):
    # "correct", "incorrect" or "assisted".
    recent: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class QuestionFlag(Base):
    """A student's "this looks wrong" report. Hides the question until reviewed."""

    __tablename__ = "question_flags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
