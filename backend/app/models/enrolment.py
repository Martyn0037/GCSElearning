# backend/app/models/enrolment.py
"""What a student studies: chosen subjects, set texts, and per-topic settings."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.curriculum import TIER_ENUM, Tier


class StudentSubject(TimestampMixin, Base):
    """A subject the student has chosen (an enrolment).

    It's *active* once ``specification_id`` is set, i.e. matched to an
    imported spec; until then it's *pending* and no questions are generated
    for it (ADR-012). ``board_confirmed`` / ``tier_confirmed`` are false when
    the student said "I don't know" and a default was used, so the admin can
    check them.
    """

    __tablename__ = "student_subjects"
    __table_args__ = (
        CheckConstraint(
            "(subject_id IS NOT NULL) <> (custom_subject_name IS NOT NULL)",
            name="catalogue_or_custom",
        ),
        # A catalogue subject can be chosen once per student.
        Index(
            "uq_student_subjects_student_subject",
            "student_id",
            "subject_id",
            unique=True,
            postgresql_where=text("subject_id IS NOT NULL"),
        ),
        Index(
            "uq_student_subjects_student_custom",
            "student_id",
            text("lower(custom_subject_name)"),
            unique=True,
            postgresql_where=text("custom_subject_name IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT")
    )
    custom_subject_name: Mapped[str | None] = mapped_column(String(80))
    board_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exam_boards.id", ondelete="RESTRICT")
    )
    board_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tier: Mapped[Tier | None] = mapped_column(TIER_ENUM)
    tier_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    specification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("specifications.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class StudentSetText(TimestampMixin, Base):
    """A set text the student studies for a subject.

    Either one of the board's listed options (``set_text_option_id``), or a
    title the student typed (``custom_title``), which stays pending until the
    admin matches it to an option.
    """

    __tablename__ = "student_set_texts"
    __table_args__ = (
        CheckConstraint(
            "(set_text_option_id IS NOT NULL) OR (custom_title IS NOT NULL)",
            name="option_or_custom",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    set_text_option_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("set_text_options.id", ondelete="RESTRICT")
    )
    custom_title: Mapped[str | None] = mapped_column(String(200))
    custom_author: Mapped[str | None] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class StudentTopicSetting(Base):
    """Admin settings for one topic for one student: covered at school, and order."""

    __tablename__ = "student_topic_settings"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    taught_at_school: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Overrides the spec order when set (lower comes first).
    sort_order: Mapped[int | None] = mapped_column(Integer)
