# backend/app/learning/router.py
"""``/api/v1/practice/items/{id}/tutor`` and ``/learn`` (students only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.ai.factory import build_gateway
from app.auth import rate_limit
from app.auth.dependencies import (
    ClockDep,
    NowDep,
    SessionDep,
    SettingsDep,
    require_csrf,
    require_roles,
)
from app.auth.rate_limit import RateLimit
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.learning.learn import card_for_item
from app.learning.schemas import LearnCardOut, TutorAsk, TutorThreadOut
from app.learning.tutor import TutorService
from app.models.user import Role, User

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/practice/items",
    tags=["learning"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

StudentDep = Annotated[User, Depends(require_roles(Role.STUDENT))]
# Each tutor message is a Claude call: limited per student, on top of the budget.
TUTOR_MINUTE_LIMIT = RateLimit(limit=8, window_seconds=60)
TUTOR_DAILY_LIMIT = RateLimit(limit=120, window_seconds=86_400)


def _tutor(
    request: Request, session: SessionDep, settings: SettingsDep, now: NowDep, clock: ClockDep
) -> TutorService:
    gateway = build_gateway(
        settings,
        request.app.state.session_factory,
        request.app.state.llm_client,
        request.app.state.circuit,
        clock,
    )
    return TutorService(session, gateway, settings, now)


TutorDep = Annotated[TutorService, Depends(_tutor)]


@router.get("/{item_id}/tutor", response_model=TutorThreadOut, operation_id="getTutorThread")
async def get_thread(item_id: uuid.UUID, student: StudentDep, tutor: TutorDep) -> TutorThreadOut:
    """The "Ask about this question" conversation so far."""
    return await tutor.thread(student.id, item_id)


@router.post("/{item_id}/tutor", response_model=TutorThreadOut, operation_id="askTutor")
async def ask(
    item_id: uuid.UUID,
    body: TutorAsk,
    student: StudentDep,
    tutor: TutorDep,
    session: SessionDep,
    now: NowDep,
) -> TutorThreadOut:
    """Ask the tutor about this question. Off-topic messages get a polite redirect."""
    await rate_limit.hit(session, f"tutor-minute:{student.id}", TUTOR_MINUTE_LIMIT, now)
    await rate_limit.hit(session, f"tutor-day:{student.id}", TUTOR_DAILY_LIMIT, now)
    return await tutor.ask(student.id, item_id, body.message)


@router.get("/{item_id}/learn", response_model=LearnCardOut, operation_id="getLearnCard")
async def learn(
    item_id: uuid.UUID, student: StudentDep, session: SessionDep, settings: SettingsDep, now: NowDep
) -> LearnCardOut:
    """A short explanation and worked example for this question's skill.

    409 ``LEARN_PREPARING`` while it's being written (try again shortly).
    """
    return await card_for_item(session, settings, student.id, item_id, now)
