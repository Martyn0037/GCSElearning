# backend/app/practice/me_router.py
"""``/api/v1/me`` read endpoints for mistakes, reviews and progress (students only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import NowDep, SessionDep, require_roles
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Cursor
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.models.user import Role, User
from app.practice import insights
from app.practice.insight_schemas import (
    MistakeOut,
    MistakePage,
    MistakeTopicGroup,
    ProgressOut,
    ReviewSummaryOut,
)

router = APIRouter(prefix=f"{API_V1_PREFIX}/me", tags=["progress"], responses=ERROR_RESPONSES)

StudentDep = Annotated[User, Depends(require_roles(Role.STUDENT))]


@router.get("/mistakes", response_model=MistakePage, operation_id="listMyMistakes")
async def list_mistakes(
    student: StudentDep,
    session: SessionDep,
    fixed: Annotated[bool, Query(description="Fixed mistakes instead of open ones")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> MistakePage:
    """The student's mistakes, newest first."""
    return await insights.list_mistakes(
        session,
        student.id,
        resolved=fixed,
        limit=limit,
        cursor=Cursor.decode(cursor) if cursor else None,
    )


@router.get(
    "/mistakes/summary", response_model=list[MistakeTopicGroup], operation_id="myMistakeGroups"
)
async def mistake_summary(student: StudentDep, session: SessionDep) -> list[MistakeTopicGroup]:
    """Mistake counts by topic and misconception (bounded by the number of topics)."""
    return await insights.mistake_groups(session, student.id)


@router.get("/mistakes/{mistake_id}", response_model=MistakeOut, operation_id="getMyMistake")
async def get_mistake(
    mistake_id: uuid.UUID, student: StudentDep, session: SessionDep
) -> MistakeOut:
    """One mistake, including its explanation once ready."""
    return await insights.get_mistake(session, student.id, mistake_id)


@router.get("/reviews/summary", response_model=ReviewSummaryOut, operation_id="myReviewSummary")
async def review_summary(student: StudentDep, session: SessionDep, now: NowDep) -> ReviewSummaryOut:
    """How many mistakes are due for review today."""
    return await insights.review_summary(session, student.id, now)


@router.get(
    "/subjects/{enrolment_id}/progress",
    response_model=ProgressOut,
    operation_id="mySubjectProgress",
)
async def subject_progress(
    enrolment_id: uuid.UUID, student: StudentDep, session: SessionDep, now: NowDep
) -> ProgressOut:
    """Mastery by topic, 30 days of activity, strongest and weakest skills."""
    return await insights.progress(session, student.id, enrolment_id, now)
