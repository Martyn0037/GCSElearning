# backend/app/gamification/router.py
"""Endpoints for the home dashboard, badges, challenges and grade boundaries."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import rate_limit
from app.auth.dependencies import NowDep, SessionDep, require_csrf, require_roles
from app.auth.rate_limit import RateLimit
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.gamification import boundaries
from app.gamification.challenges import ChallengeService
from app.gamification.dashboard import all_badges, dashboard
from app.gamification.schemas import (
    BadgeOut,
    ChallengeOut,
    DashboardOut,
    GradeBoundariesIn,
    GradeBoundariesOut,
)
from app.models.user import Role, User
from app.practice.schemas import PracticeItemOut

StudentDep = Annotated[User, Depends(require_roles(Role.STUDENT))]
AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]
# Starting a challenge picks several questions and may queue generation.
START_LIMIT = RateLimit(limit=20, window_seconds=60)

me_router = APIRouter(prefix=f"{API_V1_PREFIX}/me", tags=["progress"], responses=ERROR_RESPONSES)
challenge_router = APIRouter(
    prefix=f"{API_V1_PREFIX}/practice",
    tags=["challenges"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)
admin_router = APIRouter(
    prefix=f"{API_V1_PREFIX}/admin",
    tags=["admin"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)


def _service(session: SessionDep, now: NowDep) -> ChallengeService:
    return ChallengeService(session, now)


ServiceDep = Annotated[ChallengeService, Depends(_service)]


@me_router.get("/dashboard", response_model=DashboardOut, operation_id="myDashboard")
async def get_dashboard(student: StudentDep, session: SessionDep, now: NowDep) -> DashboardOut:
    """Level, streak, today's challenge, reviews due and where "Continue" goes."""
    return await dashboard(session, student.id, now)


@me_router.get("/badges", response_model=list[BadgeOut], operation_id="myBadges")
async def get_badges(student: StudentDep, session: SessionDep) -> list[BadgeOut]:
    """Every badge, with when it was earned (bounded: the catalogue is small)."""
    return await all_badges(session, student.id)


@challenge_router.post("/challenges/daily", response_model=ChallengeOut, operation_id="startDaily")
async def start_daily(
    student: StudentDep, service: ServiceDep, session: SessionDep, now: NowDep
) -> ChallengeOut:
    """Today's daily challenge (created on first request). Safe to repeat."""
    await rate_limit.hit(session, f"challenge-start:{student.id}", START_LIMIT, now)
    return await service.start_daily(student.id)


@challenge_router.post(
    "/enrolments/{enrolment_id}/topics/{topic_id}/boss",
    response_model=ChallengeOut,
    operation_id="startBossBattle",
)
async def start_boss(
    enrolment_id: uuid.UUID,
    topic_id: uuid.UUID,
    student: StudentDep,
    service: ServiceDep,
    session: SessionDep,
    now: NowDep,
) -> ChallengeOut:
    """Start a topic's timed boss battle, or return the one in progress."""
    await rate_limit.hit(session, f"challenge-start:{student.id}", START_LIMIT, now)
    return await service.start_boss(student.id, enrolment_id, topic_id)


@challenge_router.get(
    "/challenges/{challenge_id}", response_model=ChallengeOut, operation_id="getChallenge"
)
async def get_challenge(
    challenge_id: uuid.UUID, student: StudentDep, service: ServiceDep
) -> ChallengeOut:
    """A challenge's progress, or its results once finished."""
    return await service.get(student.id, challenge_id)


@challenge_router.post(
    "/challenges/{challenge_id}/next",
    response_model=PracticeItemOut,
    operation_id="nextChallengeItem",
)
async def next_challenge_item(
    challenge_id: uuid.UUID, student: StudentDep, service: ServiceDep
) -> PracticeItemOut:
    """The next unanswered question. 409 ``CHALLENGE_FINISHED`` or ``TIME_UP`` when done."""
    return await service.next_item(student.id, challenge_id)


@challenge_router.post(
    "/challenges/{challenge_id}/finish",
    response_model=ChallengeOut,
    operation_id="finishChallenge",
)
async def finish_challenge(
    challenge_id: uuid.UUID, student: StudentDep, service: ServiceDep
) -> ChallengeOut:
    """End a boss battle now and see the results. Safe to repeat."""
    return await service.finish(student.id, challenge_id)


@admin_router.get(
    "/specifications/{specification_id}/grade-boundaries",
    response_model=list[GradeBoundariesOut],
    operation_id="listGradeBoundaries",
)
async def list_grade_boundaries(
    specification_id: uuid.UUID, admin: AdminDep, session: SessionDep
) -> list[GradeBoundariesOut]:
    """Grade boundaries for a spec, by tier."""
    return await boundaries.list_boundaries(session, specification_id)


@admin_router.put(
    "/specifications/{specification_id}/grade-boundaries",
    response_model=GradeBoundariesOut,
    operation_id="replaceGradeBoundaries",
)
async def replace_grade_boundaries(
    specification_id: uuid.UUID, body: GradeBoundariesIn, admin: AdminDep, session: SessionDep
) -> GradeBoundariesOut:
    """Replace one tier's boundaries; an empty list clears them."""
    return await boundaries.replace_boundaries(session, specification_id, body)
