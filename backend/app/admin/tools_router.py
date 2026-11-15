# backend/app/admin/tools_router.py
"""``/api/v1/admin`` review queue and cost dashboard (admins only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.admin import tools
from app.admin.tools_schemas import (
    CostsOut,
    ReviewDecision,
    ReviewLearnCardOut,
    ReviewQuestionPage,
)
from app.auth.dependencies import NowDep, SessionDep, SettingsDep, require_csrf, require_roles
from app.core.errors import InvalidRequestError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Cursor
from app.core.schemas import API_V1_PREFIX, ERROR_RESPONSES
from app.models.question import QuestionStatus
from app.models.user import Role, User

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/admin",
    tags=["admin"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_csrf)],
)

AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("/review/questions", response_model=ReviewQuestionPage, operation_id="reviewQueue")
async def review_queue(
    _: AdminDep,
    session: SessionDep,
    status_filter: Annotated[
        QuestionStatus | None, Query(alias="status", description="pending_review or flagged")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> ReviewQuestionPage:
    """Questions waiting for review: new ones (strict mode) and ones the student flagged."""
    if status_filter is not None and status_filter not in tools.REVIEWABLE:
        raise InvalidRequestError("Status must be pending_review or flagged.")
    return await tools.review_queue(
        session,
        status=status_filter,
        limit=limit,
        cursor=Cursor.decode(cursor) if cursor else None,
    )


@router.post(
    "/review/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="decideQuestion",
)
async def decide_question(
    question_id: uuid.UUID, body: ReviewDecision, admin: AdminDep, session: SessionDep, now: NowDep
) -> Response:
    """Approve (serve it), reject or retire a question; its flags are resolved."""
    await tools.decide_question(session, admin.id, question_id, body.action, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/review/learn-cards",
    response_model=list[ReviewLearnCardOut],
    operation_id="learnCardQueue",
)
async def learn_card_queue(_: AdminDep, session: SessionDep) -> list[ReviewLearnCardOut]:
    """Learn cards waiting for review (strict mode)."""
    return await tools.learn_card_queue(session)


@router.post(
    "/review/learn-cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="decideLearnCard",
)
async def decide_learn_card(
    card_id: uuid.UUID, body: ReviewDecision, admin: AdminDep, session: SessionDep, now: NowDep
) -> Response:
    """Approve or reject a learn card (rejecting lets a new one be written)."""
    if body.action == "retire":
        raise InvalidRequestError("Learn cards can be approved or rejected.")
    await tools.decide_learn_card(session, admin.id, card_id, body.action, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/costs", response_model=CostsOut, operation_id="aiCosts")
async def costs(_: AdminDep, session: SessionDep, settings: SettingsDep, now: NowDep) -> CostsOut:
    """Claude spend today and this month against the caps, by purpose and by day."""
    return await tools.costs(session, settings, now)
