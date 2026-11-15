# backend/app/models/question.py
"""The question bank, practice items, per-objective progress and flags."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
    # Set when this item is a spaced-review of an earlier mistake.
    mistake_id: Mapped[uuid.UUID | None] = mapped_column(
        # mistakes also references practice_items; use_alter breaks the cycle.
        ForeignKey("mistakes.id", ondelete="SET NULL", use_alter=True),
        index=True,
    )
    # Set when this item is a question in a daily challenge or boss battle.
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int | None] = mapped_column(SmallInteger)


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
    correct: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # BKT estimate that the objective is mastered (ADR-005), 0..1.
    mastery: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.2"))
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


class ExplanationStatus(StrEnum):
    """Whether the "where it went wrong" explanation is ready."""

    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"  # Claude not available; the worked solution still shows


class Mistake(TimestampMixin, Base):
    """A wrong (or full-solution) answer, explained and brought back for review.

    One open mistake per student and question: getting it wrong again resets
    the schedule rather than adding a duplicate. The review schedule lives
    here (one schedule per mistake), see ``app.practice.review``.
    """

    __tablename__ = "mistakes"
    __table_args__ = (
        Index(
            "uq_mistakes_open_per_question",
            "user_id",
            "question_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        # "Reviews due" query.
        Index(
            "ix_mistakes_due",
            "user_id",
            "next_review_on",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("ix_mistakes_user_created", "user_id", "created_at"),
        CheckConstraint("review_stage BETWEEN 0 AND 10", name="review_stage_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    enrolment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_items.id", ondelete="CASCADE"), nullable=False
    )
    student_answer: Mapped[str] = mapped_column(String(200), nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(300), nullable=False)
    assisted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    misconception: Mapped[str | None] = mapped_column(String(60))
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_status: Mapped[ExplanationStatus] = mapped_column(
        _enum(ExplanationStatus, "explanation_status"), nullable=False
    )
    review_stage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    correct_streak: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    next_review_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
