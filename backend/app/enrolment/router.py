# backend/app/enrolment/router.py
"""Student-facing endpoints: catalogue, my subjects, topic map."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import (
    CurrentUserDep,
    NowDep,
    SessionDep,
    require_csrf,
    require_roles,
)
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.enrolment.schemas import CatalogueOut, MySubjectsOut, SubjectChoices, TopicMapOut
from app.enrolment.service import EnrolmentService, load_catalogue
from app.models.user import Role, User

router = APIRouter(prefix=API_V1_PREFIX, tags=["subjects"], responses=ERROR_RESPONSES)

StudentDep = Annotated[User, Depends(require_roles(Role.STUDENT))]


@router.get("/catalogue", response_model=CatalogueOut, operation_id="getCatalogue")
async def get_catalogue(_: CurrentUserDep, session: SessionDep) -> CatalogueOut:
    """Boards, subjects and current specs for the setup screen."""
    return await load_catalogue(session)


@router.get("/me/subjects", response_model=MySubjectsOut, operation_id="getMySubjects")
async def get_my_subjects(student: StudentDep, session: SessionDep, now: NowDep) -> MySubjectsOut:
    """The student's chosen subjects and their status."""
    subjects = await EnrolmentService(session, now).list_for_student(student.id)
    return MySubjectsOut(setup_completed=student.setup_completed, subjects=subjects)


@router.put(
    "/me/subjects",
    response_model=MySubjectsOut,
    operation_id="replaceMySubjects",
    dependencies=[Depends(require_csrf)],
)
async def replace_my_subjects(
    body: SubjectChoices, student: StudentDep, session: SessionDep, now: NowDep
) -> MySubjectsOut:
    """Save the setup screen. Replaces the whole list; safe to repeat."""
    subjects = await EnrolmentService(session, now).replace_choices(student, body)
    return MySubjectsOut(setup_completed=True, subjects=subjects)


@router.get(
    "/me/subjects/{enrolment_id}/topics",
    response_model=TopicMapOut,
    operation_id="getMyTopicMap",
)
async def get_my_topic_map(
    enrolment_id: uuid.UUID, student: StudentDep, session: SessionDep, now: NowDep
) -> TopicMapOut:
    """The topic map for one of the student's active subjects."""
    service = EnrolmentService(session, now)
    enrolment = await service.get_for_student(student.id, enrolment_id)
    return await service.topic_map(enrolment)
