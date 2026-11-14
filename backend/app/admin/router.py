# backend/app/admin/router.py
"""``/api/v1/admin`` endpoints (admin role only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import NowDep, SessionDep, SettingsDep, require_csrf, require_roles
from app.auth.schemas import ResetPasswordRequest
from app.auth.service import AuthService
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.models.user import Role, User

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/admin",
    tags=["admin"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.post(
    "/students/{student_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="resetStudentPassword",
)
async def reset_student_password(
    student_id: uuid.UUID,
    body: ResetPasswordRequest,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
) -> Response:
    """Set a student's password and sign them out of every device."""
    await AuthService(session, settings, now).admin_reset_password(
        admin, student_id, body.new_password
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
