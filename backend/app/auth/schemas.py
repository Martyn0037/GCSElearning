# backend/app/auth/schemas.py
"""Request and response bodies for auth and user endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import Field, field_validator, model_validator

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


# Lower-case letters, digits, dots, hyphens and underscores; starts with a letter
# or digit; 3-32 characters. No "@", so a username can never look like an email.
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,31}$"
MAX_DISPLAY_NAME_LENGTH = 40
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class StudentUpdate(ApiModel):
    """An admin changing a student's name and/or username. Send at least one."""

    display_name: str | None = Field(
        default=None,
        max_length=MAX_DISPLAY_NAME_LENGTH,
        description="What the app calls the student, e.g. on the home screen.",
    )
    username: str | None = Field(
        default=None, max_length=32, description="What the student signs in with."
    )

    @field_validator("display_name")
    @classmethod
    def _clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name can't be blank")
        if _CONTROL_CHARS.search(value):
            raise ValueError("Name can't contain control characters")
        return value

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not re.fullmatch(USERNAME_PATTERN, value):
            raise ValueError(
                "Use 3-32 lower-case letters, digits, dots, hyphens or underscores, "
                "starting with a letter or digit"
            )
        return value

    @model_validator(mode="after")
    def _something_to_change(self) -> StudentUpdate:
        if self.display_name is None and self.username is None:
            raise ValueError("Send a new name, a new username, or both")
        return self
