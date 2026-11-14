# backend/app/users/router.py
"""``/api/v1/users`` endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.auth.dependencies import CurrentUserDep, SessionDep, ensure_can_access_user
from app.auth.schemas import UserOut
from app.core.errors import NotFoundError
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.models.user import User

router = APIRouter(prefix=f"{API_V1_PREFIX}/users", tags=["users"], responses=ERROR_RESPONSES)


@router.get("/me", response_model=UserOut, operation_id="getCurrentUser")
async def get_me(user: CurrentUserDep) -> UserOut:
    """Return the signed-in user."""
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut, operation_id="getUser")
async def get_user(user_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep) -> UserOut:
    """Return a user the caller is allowed to see.

    Admins can see anyone; guardians their linked students; others only
    themselves. Anything else is reported as not found.
    """
    await ensure_can_access_user(session, actor, user_id)
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    return UserOut.model_validate(target)
