# backend/app/admin/router.py
"""``/api/v1/admin`` endpoints (admin role only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.auth.dependencies import NowDep, SessionDep, SettingsDep, require_csrf, require_roles
from app.auth.schemas import AdminStudentOut, ResetPasswordRequest, StudentUpdate
from app.auth.service import AuthService
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Cursor
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.enrolment.schemas import (
    AdminEnrolmentOut,
    AdminEnrolmentPage,
    AdminSpecificationOut,
    EnrolmentUpdate,
    SetTextUpdate,
    TopicMapOut,
    TopicOrderUpdate,
    TopicSettingUpdate,
)
from app.enrolment.service import EnrolmentService
from app.models.user import Role, User

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/admin",
    tags=["admin"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("/students", response_model=list[AdminStudentOut], operation_id="listStudents")
async def list_students(
    _: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> list[AdminStudentOut]:
    """Student accounts, by name, with whether sign-in is locked."""
    students = await AuthService(session, settings, now).list_students(limit)
    return [_student_out(s, now) for s in students]


def _student_out(student: User, now: datetime) -> AdminStudentOut:
    locked = student.locked_until if student.locked_until and student.locked_until > now else None
    return AdminStudentOut(
        id=student.id,
        display_name=student.display_name,
        username=student.username,
        locked_until=locked,
    )


@router.patch(
    "/students/{student_id}", response_model=AdminStudentOut, operation_id="updateStudent"
)
async def update_student(
    student_id: uuid.UUID,
    body: StudentUpdate,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
) -> AdminStudentOut:
    """Change a student's name and/or username. Their progress and sessions are kept."""
    student = await AuthService(session, settings, now).admin_update_student(
        admin, student_id, display_name=body.display_name, username=body.username
    )
    return _student_out(student, now)


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


# ---------------------------------------------------------------- curriculum & enrolments


@router.get(
    "/specifications",
    response_model=list[AdminSpecificationOut],
    operation_id="listSpecifications",
)
async def list_specifications(
    _: AdminDep, session: SessionDep, now: NowDep
) -> list[AdminSpecificationOut]:
    """Every imported spec version with its content counts."""
    return await EnrolmentService(session, now).list_specifications()


@router.get("/enrolments", response_model=AdminEnrolmentPage, operation_id="listEnrolments")
async def list_enrolments(
    _: AdminDep,
    session: SessionDep,
    now: NowDep,
    attention: Annotated[bool, Query(description="Only those needing the admin")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> AdminEnrolmentPage:
    """Students' subjects, oldest first, with what needs attention."""
    return await EnrolmentService(session, now).admin_list(
        attention_only=attention,
        limit=limit,
        cursor=Cursor.decode(cursor) if cursor else None,
    )


@router.patch(
    "/enrolments/{enrolment_id}",
    response_model=AdminEnrolmentOut,
    operation_id="updateEnrolment",
)
async def update_enrolment(
    enrolment_id: uuid.UUID, body: EnrolmentUpdate, _: AdminDep, session: SessionDep, now: NowDep
) -> AdminEnrolmentOut:
    """Confirm or correct a subject's board, tier or spec version."""
    return await EnrolmentService(session, now).admin_update(enrolment_id, body)


@router.patch(
    "/set-texts/{set_text_id}",
    response_model=AdminEnrolmentOut,
    operation_id="matchSetText",
)
async def match_set_text(
    set_text_id: uuid.UUID, body: SetTextUpdate, _: AdminDep, session: SessionDep, now: NowDep
) -> AdminEnrolmentOut:
    """Match a typed-in set text to the board's list."""
    return await EnrolmentService(session, now).admin_match_set_text(set_text_id, body.option_id)


@router.delete(
    "/set-texts/{set_text_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSetText",
)
async def delete_set_text(
    set_text_id: uuid.UUID, _: AdminDep, session: SessionDep, now: NowDep
) -> Response:
    """Remove a set text (e.g. a typo). Idempotent."""
    await EnrolmentService(session, now).admin_delete_set_text(set_text_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/enrolments/{enrolment_id}/topics",
    response_model=TopicMapOut,
    operation_id="getEnrolmentTopics",
)
async def get_enrolment_topics(
    enrolment_id: uuid.UUID, _: AdminDep, session: SessionDep, now: NowDep
) -> TopicMapOut:
    """A student's topic map, for setting what's been covered at school."""
    service = EnrolmentService(session, now)
    return await service.topic_map(await service.admin_get(enrolment_id))


@router.put(
    "/enrolments/{enrolment_id}/topics/{topic_id}",
    response_model=TopicMapOut,
    operation_id="setTopicTaught",
)
async def set_topic_taught(
    enrolment_id: uuid.UUID,
    topic_id: uuid.UUID,
    body: TopicSettingUpdate,
    _: AdminDep,
    session: SessionDep,
    now: NowDep,
) -> TopicMapOut:
    """Mark a topic as covered (or not) at school. Idempotent."""
    service = EnrolmentService(session, now)
    enrolment = await service.admin_get(enrolment_id)
    return await service.set_topic_taught(enrolment, topic_id, body.taught_at_school)


@router.put(
    "/enrolments/{enrolment_id}/topic-order",
    response_model=TopicMapOut,
    operation_id="setTopicOrder",
)
async def set_topic_order(
    enrolment_id: uuid.UUID, body: TopicOrderUpdate, _: AdminDep, session: SessionDep, now: NowDep
) -> TopicMapOut:
    """Set the order topics are studied in. Idempotent."""
    service = EnrolmentService(session, now)
    enrolment = await service.admin_get(enrolment_id)
    return await service.set_topic_order(enrolment, body.topic_ids)
