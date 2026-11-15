# backend/tests/integration/test_guardian_admin_tools.py
"""Integration tests for the guardian dashboard and the admin tools (Phase 7).

Covers:
- guardian students list with consent status; give consent (current notice),
  idempotent; an older notice -> 422 POLICY_OUT_OF_DATE; withdraw keeps the
  record; all audited
- weekly summary: answers, accuracy, minutes (capped at 10 per question),
  active London days, XP, mistakes fixed, badges, boss battles, weak topics
  per subject; an earlier week is empty; weeks_ago over 11 -> 422
- export: everything about the student as a JSON download; audited
- deletion: wrong password -> 422 WRONG_PASSWORD; confirm must be "DELETE";
  success removes the student and their records; audited without personal data
- access: an unlinked student -> 404 everywhere; students and admins -> 403
- admin review queue: pending and flagged questions with hints, flags and
  verification notes; status filter; bad status -> 422; cursor paging;
  approve resolves flags and serves it; deciding twice -> 409; unknown -> 404
- learn cards: queue, approve, reject (deleted), retire -> 422
- costs: today and month in pounds, by purpose, failures, 30 days; caps;
  students -> 403
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.guardian.schemas import PRIVACY_POLICY_VERSION
from app.models.audit_log import AuditLog
from app.models.curriculum import Tier
from app.models.gamification import (
    Challenge,
    ChallengeKind,
    ChallengeStatus,
    UserBadge,
    XpEvent,
    XpSource,
)
from app.models.learning import LearnCard, LearnCardStatus
from app.models.ops import AiUsage, UsageStatus
from app.models.question import (
    Mistake,
    ObjectiveProgress,
    PracticeItem,
    Question,
    QuestionFlag,
    QuestionStatus,
)
from app.models.user import GuardianLink, Role, User
from app.practice.review import london_today
from tests.fixtures.factories import FakeClock, create_question, create_user
from tests.integration.helpers import csrf_headers, error_code, login
from tests.integration.test_practice_api import Setup, setup

pytestmark = pytest.mark.integration
__all__ = ["setup"]

GUARDIAN = "parent@example.test"


@pytest.fixture
async def guardian(
    other_client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> httpx.AsyncClient:
    """A signed-in guardian linked to the setup student."""
    parent = await create_user(session, Role.GUARDIAN, identifier=GUARDIAN)
    session.add(GuardianLink(guardian_id=parent.id, student_id=setup.student_id))
    await session.commit()
    assert (await login(other_client, GUARDIAN)).status_code == 200
    return other_client


def _base(setup: Setup) -> str:
    return f"/api/v1/guardian/students/{setup.student_id}"


async def _audit(session: AsyncSession, action: str) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ) or 0


# --------------------------------------------------------------------- guardian


async def test_guardian_should_give_and_withdraw_consent(
    guardian: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Act
    before = (await guardian.get("/api/v1/guardian/students")).json()
    path = f"{_base(setup)}/consent"
    body = {"policyVersion": PRIVACY_POLICY_VERSION}
    given = await guardian.post(path, json=body, headers=csrf_headers(guardian))
    again = await guardian.post(path, json=body, headers=csrf_headers(guardian))
    old = await guardian.post(
        path, json={"policyVersion": "2020-01"}, headers=csrf_headers(guardian)
    )
    withdrawn = await guardian.delete(path, headers=csrf_headers(guardian))

    # Assert
    assert before[0]["consent"]["granted"] is False
    assert before[0]["currentPolicyVersion"] == PRIVACY_POLICY_VERSION
    assert given.json()["granted"] is True
    assert again.json()["grantedAt"] == given.json()["grantedAt"]
    assert error_code(old) == "POLICY_OUT_OF_DATE"
    assert withdrawn.json()["granted"] is False
    assert await _audit(session, "consent.granted") == 1
    assert await _audit(session, "consent.withdrawn") == 1


async def test_weekly_summary_should_add_up_the_week(
    guardian: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange: two answers this week (one left open for two hours), last week one
    now = clock.now()
    question = await create_question(session, setup.a1, tier="foundation")
    for served, answered, correct in [
        (now - timedelta(minutes=3), now, True),
        (now - timedelta(hours=2), now - timedelta(minutes=1), False),
        (now - timedelta(days=8), now - timedelta(days=8), True),
    ]:
        session.add(
            PracticeItem(
                user_id=setup.student_id,
                enrolment_id=setup.enrolment_id,
                question_id=question,
                difficulty=1,
                served_at=served,
                answered_at=answered,
                correct=correct,
                assisted=False,
            )
        )
    session.add(
        XpEvent(
            user_id=setup.student_id,
            source=XpSource.ANSWER,
            ref_id=uuid.uuid4(),
            amount=30,
            created_at=now,
        )
    )
    session.add(UserBadge(user_id=setup.student_id, badge_code="century", awarded_at=now))
    session.add(
        Challenge(
            user_id=setup.student_id,
            kind=ChallengeKind.BOSS,
            status=ChallengeStatus.COMPLETED,
            london_date=london_today(now),
            enrolment_id=setup.enrolment_id,
            topic_id=setup.algebra,
            started_at=now,
            completed_at=now,
            score=3,
            max_score=4,
            percent=75.0,
        )
    )
    session.add(
        ObjectiveProgress(
            user_id=setup.student_id,
            objective_id=setup.a1,
            level=1,
            recent=[],
            attempts=3,
            correct=1,
            mastery=0.3,
        )
    )
    await session.flush()
    item_id = await session.scalar(select(PracticeItem.id).limit(1))
    session.add(
        Mistake(
            user_id=setup.student_id,
            enrolment_id=setup.enrolment_id,
            question_id=question,
            objective_id=setup.a1,
            source_item_id=item_id,
            student_answer="A",
            correct_answer="C",
            assisted=False,
            explanation_status="unavailable",
            next_review_on=london_today(now),
            resolved_at=now,
        )
    )
    await session.commit()

    # Act
    week = (await guardian.get(f"{_base(setup)}/summary")).json()
    last = (await guardian.get(f"{_base(setup)}/summary?weeks_ago=1")).json()
    too_far = await guardian.get(f"{_base(setup)}/summary?weeks_ago=12")

    # Assert
    assert (week["answered"], week["correct"], week["minutes"]) == (2, 1, 13)
    assert week["activeDays"] == [str(london_today(now))]
    assert (week["xp"], week["mistakesFixed"], week["badges"]) == (30, 1, ["Century"])
    assert week["bossBattles"] == [{"topicTitle": "Algebra", "percent": 75.0}]
    maths = week["subjects"][0]
    assert (maths["answered"], maths["correct"]) == (2, 1)
    assert maths["weakTopics"][0]["title"] == "Algebra"
    assert last["answered"] == 1
    assert too_far.status_code == 422


async def test_export_should_download_the_students_data(
    guardian: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    response = await guardian.get(f"{_base(setup)}/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["student"]["username"] == "sam10"
    assert {"answers", "mistakes", "xp", "tutor_messages", "consents", "set_texts"} <= set(data)
    assert await _audit(session, "data.exported") == 1


async def test_deleting_a_student_should_need_the_password_and_remove_everything(
    guardian: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    question = await create_question(session, setup.a1, tier="foundation")
    session.add(
        PracticeItem(
            user_id=setup.student_id,
            enrolment_id=setup.enrolment_id,
            question_id=question,
            difficulty=1,
            served_at=func.now(),
        )
    )
    await session.commit()
    path = f"{_base(setup)}/delete"

    # Act
    wrong = await guardian.post(
        path, json={"confirm": "DELETE", "password": "nope"}, headers=csrf_headers(guardian)
    )
    unconfirmed = await guardian.post(
        path, json={"confirm": "yes", "password": "x"}, headers=csrf_headers(guardian)
    )
    from tests.fixtures.factories import DEFAULT_PASSWORD

    done = await guardian.post(
        path,
        json={"confirm": "DELETE", "password": DEFAULT_PASSWORD},
        headers=csrf_headers(guardian),
    )

    # Assert
    assert error_code(wrong) == "WRONG_PASSWORD"
    assert unconfirmed.status_code == 422
    assert done.status_code == 204
    session.expire_all()
    assert await session.get(User, setup.student_id) is None
    assert await session.scalar(select(func.count()).select_from(PracticeItem)) == 0
    entry = await session.scalar(select(AuditLog).where(AuditLog.action == "student.deleted"))
    assert entry is not None
    assert entry.details == {"student_id": str(setup.student_id)}


async def test_guardians_should_only_reach_linked_students(
    guardian: httpx.AsyncClient, session: AsyncSession
) -> None:
    other = await create_user(session, Role.STUDENT, identifier="stranger")
    base = f"/api/v1/guardian/students/{other.id}"
    responses = [
        await guardian.get(f"{base}/summary"),
        await guardian.get(f"{base}/export"),
        await guardian.post(
            f"{base}/consent",
            json={"policyVersion": PRIVACY_POLICY_VERSION},
            headers=csrf_headers(guardian),
        ),
        await guardian.post(
            f"{base}/delete",
            json={"confirm": "DELETE", "password": "x"},
            headers=csrf_headers(guardian),
        ),
    ]
    assert [r.status_code for r in responses] == [404, 404, 404, 404]


async def test_students_should_not_use_guardian_tools(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    assert (await client.get("/api/v1/guardian/students")).status_code == 403


# --------------------------------------------------------------------- admin


@pytest.fixture
async def admin(
    other_client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> httpx.AsyncClient:
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    assert (await login(other_client, "admin@example.test")).status_code == 200
    return other_client


async def test_review_queue_should_list_and_decide_questions(
    admin: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange: one pending, one flagged with a reason, one active
    pending = await create_question(session, setup.a1, tier="foundation", status="pending_review")
    flagged = await create_question(session, setup.a1, tier="foundation", status="flagged")
    await create_question(session, setup.a1, tier="foundation")
    session.add(
        QuestionFlag(
            question_id=flagged,
            user_id=setup.student_id,
            reason="Answer is 8",
            created_at=clock.now(),
        )
    )
    await session.commit()

    # Act
    everything = (await admin.get("/api/v1/admin/review/questions")).json()
    only_flagged = (await admin.get("/api/v1/admin/review/questions?status=flagged")).json()
    bad = await admin.get("/api/v1/admin/review/questions?status=active")
    first = (await admin.get("/api/v1/admin/review/questions?limit=1")).json()
    second = (
        await admin.get(f"/api/v1/admin/review/questions?limit=1&cursor={first['nextCursor']}")
    ).json()
    approve = await admin.post(
        f"/api/v1/admin/review/questions/{flagged}",
        json={"action": "approve"},
        headers=csrf_headers(admin),
    )
    twice = await admin.post(
        f"/api/v1/admin/review/questions/{flagged}",
        json={"action": "reject"},
        headers=csrf_headers(admin),
    )
    missing = await admin.post(
        f"/api/v1/admin/review/questions/{uuid.uuid4()}",
        json={"action": "reject"},
        headers=csrf_headers(admin),
    )

    # Assert
    assert {q["id"] for q in everything["items"]} == {str(pending), str(flagged)}
    flagged_item = only_flagged["items"][0]
    assert flagged_item["flags"][0]["reason"] == "Answer is 8"
    assert len(flagged_item["hints"]) == 4
    assert flagged_item["objectiveRef"] == "A1"
    assert bad.status_code == 422
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {str(pending), str(flagged)}
    assert second["nextCursor"] is None
    assert approve.status_code == 204
    session.expire_all()
    assert (await session.get(Question, flagged)).status is QuestionStatus.ACTIVE  # type: ignore[union-attr]
    resolved = await session.scalar(select(QuestionFlag.resolved_at))
    assert resolved is not None
    assert error_code(twice) == "NOT_UNDER_REVIEW"
    assert missing.status_code == 404


async def test_learn_card_review_should_approve_and_reject(
    admin: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    cards = [
        LearnCard(
            objective_id=setup.a1,
            tier=tier,
            explanation="E",
            worked_example="W",
            status=LearnCardStatus.PENDING_REVIEW,
            generator_model="test",
        )
        for tier in (Tier.FOUNDATION, Tier.HIGHER)
    ]
    session.add_all(cards)
    await session.commit()
    base = "/api/v1/admin/review/learn-cards"

    # Act
    queue = (await admin.get(base)).json()
    approve = await admin.post(
        f"{base}/{cards[0].id}", json={"action": "approve"}, headers=csrf_headers(admin)
    )
    reject = await admin.post(
        f"{base}/{cards[1].id}", json={"action": "reject"}, headers=csrf_headers(admin)
    )
    retire = await admin.post(
        f"{base}/{cards[0].id}", json={"action": "retire"}, headers=csrf_headers(admin)
    )

    # Assert
    assert len(queue) == 2
    assert (approve.status_code, reject.status_code, retire.status_code) == (204, 204, 422)
    session.expire_all()
    statuses = (await session.scalars(select(LearnCard.status))).all()
    assert statuses == [LearnCardStatus.ACTIVE]


async def test_costs_should_add_up_spend_against_the_caps(
    admin: httpx.AsyncClient, client: httpx.AsyncClient, session: AsyncSession, clock: FakeClock
) -> None:
    # Arrange
    now = clock.now()
    for created, purpose, status, cost in [
        (now, "generate_question", UsageStatus.SETTLED, "0.10"),
        (now, "tutor", UsageStatus.FAILED, "0.00"),
        (now - timedelta(days=40), "tutor", UsageStatus.SETTLED, "5.00"),
    ]:
        session.add(
            AiUsage(
                created_at=created,
                purpose=purpose,
                model="m",
                status=status,
                reserved_usd=Decimal("0.2"),
                cost_usd=Decimal(cost),
            )
        )
    await session.commit()

    # Act
    costs = (await admin.get("/api/v1/admin/costs")).json()
    forbidden = await client.get("/api/v1/admin/costs")  # the student

    # Assert
    assert (costs["todayGbp"], costs["monthGbp"]) == ("0.09", "0.09")
    assert (costs["monthCalls"], costs["monthFailures"]) == (2, 1)
    assert costs["byPurpose"][0]["purpose"] == "generate_question"
    assert len(costs["last30Days"]) == 30
    assert costs["last30Days"][-1]["calls"] == 2
    assert costs["apiKeyConfigured"] is False
    assert forbidden.status_code == 403
