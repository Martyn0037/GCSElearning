# backend/app/models/learning.py
"""Learn cards and tutor conversations (ADR-018)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.curriculum import TIER_ENUM, Tier


def _enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda e: [m.value for m in e])


class LearnCardStatus(StrEnum):
    """Only ``active`` cards are shown; strict mode holds new ones for review."""

    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    REJECTED = "rejected"


class LearnCard(TimestampMixin, Base):
    """A short explanation and worked example for one objective on one tier.

    Generated once, cached, and reviewable by the admin.
    """

    __tablename__ = "learn_cards"
    __table_args__ = (UniqueConstraint("objective_id", "tier", postgresql_nulls_not_distinct=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[Tier | None] = mapped_column(TIER_ENUM)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    worked_example: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LearnCardStatus] = mapped_column(
        _enum(LearnCardStatus, "learn_card_status"), nullable=False
    )
    generator_model: Mapped[str] = mapped_column(String(64), nullable=False)


class TutorRole(StrEnum):
    """Who wrote a tutor message."""

    STUDENT = "student"
    TUTOR = "tutor"


class TutorMessage(Base):
    """One message in the "Ask about this question" conversation for a practice item."""

    __tablename__ = "tutor_messages"
    __table_args__ = (UniqueConstraint("item_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Order within the conversation (1, 2, ...): timestamps can tie.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    role: Mapped[TutorRole] = mapped_column(_enum(TutorRole, "tutor_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    on_topic: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
