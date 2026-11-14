# backend/app/models/user.py
"""Users, roles, and guardian-to-student links."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Role(StrEnum):
    """What a user is allowed to do."""

    STUDENT = "student"
    GUARDIAN = "guardian"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    """An account.

    Students sign in with a username and have no email (data minimisation).
    Guardians and admins sign in with an email. Only a first name or nickname
    is stored as the display name.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'student' AND username IS NOT NULL AND email IS NULL)"
            " OR (role <> 'student' AND email IS NOT NULL)",
            name="login_identifier_matches_role",
        ),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # Stored lower-cased; uniqueness is enforced on the lower-cased value.
    username: Mapped[str | None] = mapped_column(String(32), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When a student finished the subject setup screen; None until then.
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'Europe/London'")
    )

    @property
    def setup_completed(self) -> bool:
        """Whether the student has finished the subject setup screen."""
        return self.setup_completed_at is not None


class GuardianLink(Base):
    """Grants a guardian read access to one student's progress."""

    __tablename__ = "guardian_links"

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
