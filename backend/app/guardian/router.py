# backend/app/guardian/router.py
"""``/api/v1/guardian`` endpoints (guardians only)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse

from app.auth import rate_limit
from app.auth.dependencies import NowDep, SessionDep, require_csrf, require_roles
from app.auth.rate_limit import RateLimit
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.guardian.schemas import (
    ConsentIn,
    ConsentOut,
    DeleteStudentIn,
    LinkedStudentOut,
    WeeklySummaryOut,
)
from app.guardian.service import MAX_WEEKS_BACK, GuardianService
from app.models.user import Role, User

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/guardian",
    tags=["guardian"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

GuardianDep = Annotated[User, Depends(require_roles(Role.GUARDIAN))]
# Password re-entry for deletion: limited like login.
DELETE_LIMIT = RateLimit(limit=5, window_seconds=900)


def _service(session: SessionDep, now: NowDep) -> GuardianService:
    return GuardianService(session, now)


ServiceDep = Annotated[GuardianService, Depends(_service)]


@router.get("/students", response_model=list[LinkedStudentOut], operation_id="myStudents")
async def students(guardian: GuardianDep, service: ServiceDep) -> list[LinkedStudentOut]:
    """Students linked to this guardian, with consent status."""
    return await service.students(guardian.id)


@router.get(
    "/students/{student_id}/summary",
    response_model=WeeklySummaryOut,
    operation_id="studentWeeklySummary",
)
async def summary(
    student_id: uuid.UUID,
    guardian: GuardianDep,
    service: ServiceDep,
    weeks_ago: Annotated[int, Query(ge=0, le=MAX_WEEKS_BACK)] = 0,
) -> WeeklySummaryOut:
    """A week of the student's activity (this week by default)."""
    return await service.weekly_summary(guardian.id, student_id, weeks_ago)


@router.post(
    "/students/{student_id}/consent", response_model=ConsentOut, operation_id="giveConsent"
)
async def give_consent(
    student_id: uuid.UUID, body: ConsentIn, guardian: GuardianDep, service: ServiceDep
) -> ConsentOut:
    """Agree to the current privacy notice for this student."""
    return await service.give_consent(guardian.id, student_id, body.policy_version)


@router.delete(
    "/students/{student_id}/consent", response_model=ConsentOut, operation_id="withdrawConsent"
)
async def withdraw_consent(
    student_id: uuid.UUID, guardian: GuardianDep, service: ServiceDep
) -> ConsentOut:
    """Withdraw consent. The record of what was agreed is kept."""
    return await service.withdraw_consent(guardian.id, student_id)


@router.get(
    "/students/{student_id}/export",
    operation_id="exportStudentData",
    responses={200: {"content": {"application/json": {}}, "description": "All the student's data"}},
)
async def export(student_id: uuid.UUID, guardian: GuardianDep, service: ServiceDep) -> Response:
    """Download everything stored about the student, as a JSON file."""
    data: dict[str, Any] = await service.export(guardian.id, student_id)
    return JSONResponse(
        data,
        headers={"Content-Disposition": f'attachment; filename="gcse-coach-{student_id}.json"'},
    )


@router.post(
    "/students/{student_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteStudent",
)
async def delete_student(
    student_id: uuid.UUID,
    body: DeleteStudentIn,
    guardian: GuardianDep,
    service: ServiceDep,
    session: SessionDep,
    now: NowDep,
) -> Response:
    """Permanently delete the student's account and data (password and "DELETE" required)."""
    await rate_limit.hit(session, f"guardian-delete:{guardian.id}", DELETE_LIMIT, now)
    await service.delete_student(guardian, student_id, body.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
