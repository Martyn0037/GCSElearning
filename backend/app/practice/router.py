# backend/app/practice/router.py
"""``/api/v1/practice`` endpoints (students only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.ai.factory import build_generator
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
from app.models.user import Role, User
from app.practice.schemas import AnswerRequest, AnswerResultOut, FlagRequest, PracticeItemOut
from app.practice.service import PracticeService

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/practice",
    tags=["practice"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

StudentDep = Annotated[User, Depends(require_roles(Role.STUDENT))]
# "Next question" may call Claude when the bank is empty, so it's limited per user.
NEXT_LIMIT = RateLimit(limit=30, window_seconds=60)
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
]


def _service(
    request: Request, session: SessionDep, settings: SettingsDep, now: NowDep, clock: ClockDep
) -> PracticeService:
    generator = build_generator(
        settings,
        request.app.state.session_factory,
        request.app.state.llm_client,
        request.app.state.circuit,
        clock,
    )
    return PracticeService(session, settings, now, generator)


ServiceDep = Annotated[PracticeService, Depends(_service)]


@router.post(
    "/enrolments/{enrolment_id}/topics/{topic_id}/next",
    response_model=PracticeItemOut,
    operation_id="nextPracticeItem",
)
async def next_item(
    enrolment_id: uuid.UUID,
    topic_id: uuid.UUID,
    student: StudentDep,
    service: ServiceDep,
    session: SessionDep,
    now: NowDep,
) -> PracticeItemOut:
    """The current question for this topic, or a new one. Safe to repeat."""
    await rate_limit.hit(session, f"practice-next:{student.id}", NEXT_LIMIT, now)
    return await service.next_item(student.id, enrolment_id, topic_id)


@router.post("/items/{item_id}/hints", response_model=PracticeItemOut, operation_id="revealHint")
async def reveal_hint(
    item_id: uuid.UUID, student: StudentDep, service: ServiceDep
) -> PracticeItemOut:
    """Reveal the next hint ("I'm stuck"). The fourth is the full solution."""
    return await service.reveal_hint(student.id, item_id)


@router.post(
    "/items/{item_id}/answer", response_model=AnswerResultOut, operation_id="answerPracticeItem"
)
async def answer(
    item_id: uuid.UUID,
    body: AnswerRequest,
    idempotency_key: IdempotencyKey,
    student: StudentDep,
    service: ServiceDep,
) -> AnswerResultOut:
    """Mark an answer. Repeating with the same Idempotency-Key returns the same result."""
    return await service.submit(student.id, item_id, body.answer, idempotency_key)


@router.post(
    "/items/{item_id}/flag", status_code=status.HTTP_204_NO_CONTENT, operation_id="flagPracticeItem"
)
async def flag(
    item_id: uuid.UUID, body: FlagRequest, student: StudentDep, service: ServiceDep
) -> Response:
    """Report "this looks wrong". The question is hidden until reviewed."""
    await service.flag(student.id, item_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/items/{item_id}/similar", response_model=PracticeItemOut, operation_id="similarPracticeItem"
)
async def similar(
    item_id: uuid.UUID, student: StudentDep, service: ServiceDep, session: SessionDep, now: NowDep
) -> PracticeItemOut:
    """Another question on the same skill, straight after a wrong answer."""
    await rate_limit.hit(session, f"practice-next:{student.id}", NEXT_LIMIT, now)
    return await service.similar(student.id, item_id)


@router.post("/reviews/next", response_model=PracticeItemOut, operation_id="nextReviewItem")
async def next_review(student: StudentDep, service: ServiceDep) -> PracticeItemOut:
    """The next mistake due for review today (resumes an open one). Safe to repeat."""
    return await service.next_review(student.id)
