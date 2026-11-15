# backend/app/auth/schemas.py
"""Request and response bodies for auth and user endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.core.schemas import ApiModel
from app.models.user import Role


class LoginRequest(ApiModel):
    """Credentials for signing in."""

    identifier: str = Field(min_length=1, max_length=254, description="Username or email")
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserOut(ApiModel):
    """A user as visible to themselves, their guardian, or an admin."""

    id: uuid.UUID
    role: Role
    display_name: str
    username: str | None
    email: str | None
    setup_completed: bool


class SessionOut(ApiModel):
    """Returned after login or refresh. Tokens themselves travel only in cookies."""

    user: UserOut
    access_token_expires_at: datetime


class ResetPasswordRequest(ApiModel):
    """An admin setting a student's new password."""

    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class AdminStudentOut(ApiModel):
    """A student account as the admin sees it, for picking whose password to reset."""

    id: uuid.UUID
    display_name: str
    username: str | None = Field(description="What the student signs in with.")
    locked_until: datetime | None = Field(
        description="Set while sign-in is locked after too many wrong passwords."
    )
