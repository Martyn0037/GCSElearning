# backend/tests/integration/test_practice_api.py
"""Integration tests for the practice API.

Covers:
- next question: a topic not covered at school is still served; serves from the bank
  without the answer; repeating "next" returns the same open item (also when
  two requests race); generation on the spot when the bank is empty; bank
  empty + no Claude -> 409 QUESTIONS_PREPARING and generation queued
- hints: revealed one at a time up to the full solution, then 409; not after
  answering
- answering: correct/incorrect marking per type; same Idempotency-Key replays
  the result without double-counting; a different key -> 409; missing or
  malformed key, empty or over-long answer -> 422
- ladder: three correct moves up a level; full solution -> assisted, no move
- keys: number answers get the keypad; every short answer gets every symbol
  key (maths ones replace the phone keyboard, word ones don't); multiple
  choice gets none; a typed π answer
  is marked right against a LaTeX key, and the key is shown as maths
- flag: hides the question from further serving; idempotent
- access: another student's item -> 404; guardians -> 403; CSRF required
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curriculum import LearningObjective, Tier
from app.models.enrolment import StudentSubject, StudentTopicSetting
from app.models.ops import Job
from app.models.question import ObjectiveProgress, Question, QuestionStatus
from app.models.user import Role
from app.questions.answer_forms import KEYPAD_SYMBOLS
from app.questions.llm_schemas import GeneratedQuestion, Verification
from tests.fixtures.factories import (
    CurriculumIds,
    create_question,
    create_user,
    import_fixture_curriculum,
)
from tests.fixtures.fake_llm import FakeLlmClient, Reply, mcq, verification
from tests.integration.helpers import csrf_headers, error_code, login

pytestmark = pytest.mark.integration


class Setup:
    """A signed-in Foundation maths student with topic 2 (Algebra, objective A1) covered."""

    def __init__(
        self, ids: CurriculumIds, enrolment_id: uuid.UUID, student_id: uuid.UUID, a1: uuid.UUID
    ) -> None:
        self.ids = ids
        self.enrolment_id = enrolment_id
        self.student_id = student_id
        self.a1 = a1
        self.algebra = ids.topics["M1:2"]
        self.number = ids.topics["M1:1"]

    def next_path(self, topic: uuid.UUID | None = None) -> str:
        return (
            f"/api/v1/practice/enrolments/{self.enrolment_id}/topics/{topic or self.algebra}/next"
        )


@pytest.fixture
async def setup(client: httpx.AsyncClient, session: AsyncSession) -> Setup:
    ids = await import_fixture_curriculum(session)
    student = await create_user(session, Role.STUDENT, identifier="sam10")
    enrolment = StudentSubject(
        id=uuid.uuid4(),
        student_id=student.id,
        subject_id=ids.subjects["maths"],
        board_id=ids.boards["board-a"],
        board_confirmed=True,
        tier=Tier.FOUNDATION,
        tier_confirmed=True,
        specification_id=ids.specs["M1"],
        position=0,
    )
    session.add(enrolment)
    session.add(
        StudentTopicSetting(
            student_id=student.id, topic_id=ids.topics["M1:2"], taught_at_school=True
        )
    )
    await session.commit()
    a1 = await session.scalar(select(LearningObjective.id).where(LearningObjective.ref == "A1"))
    assert a1 is not None
    assert (await login(client, "sam10")).status_code == 200
    return Setup(ids, enrolment.id, student.id, a1)


async def _next(
    client: httpx.AsyncClient, setup: Setup, topic: uuid.UUID | None = None
) -> httpx.Response:
    return await client.post(setup.next_path(topic), headers=csrf_headers(client))


async def _answer(
    client: httpx.AsyncClient, item_id: str, answer: str, key: str | None = None
) -> httpx.Response:
    headers = {**csrf_headers(client), "Idempotency-Key": key or uuid.uuid4().hex}
    return await client.post(
        f"/api/v1/practice/items/{item_id}/answer", json={"answer": answer}, headers=headers
    )


async def _hint(client: httpx.AsyncClient, item_id: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/practice/items/{item_id}/hints", headers=csrf_headers(client)
    )


async def test_topic_not_covered_at_school_should_still_be_open(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange: Number isn't ticked as covered at school (ADR-021: everything is open)
    t1 = await session.scalar(select(LearningObjective.id).where(LearningObjective.ref == "T1"))
    assert t1 is not None
    await create_question(session, t1, tier="foundation", stem="What is $2 + 2$?")

    # Act
    response = await _next(client, setup, setup.number)

    # Assert
    assert response.status_code == 200
    assert response.json()["objectiveRef"] == "T1"


async def test_should_serve_bank_question_without_answer(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation", stem="Simplify $3x + 2x$.")

    response = await _next(client, setup)

    assert response.status_code == 200
    body = response.json()
    assert body["stem"] == "Simplify $3x + 2x$."
    assert [o["label"] for o in body["options"]] == ["A", "B", "C", "D"]
    assert (body["objectiveRef"], body["difficulty"], body["hints"], body["hintsRemaining"]) == (
        "A1",
        1,
        [],
        4,
    )
    assert "answer" not in body
    assert "correct" not in response.text.lower()


async def test_repeated_next_should_return_same_open_item_even_when_racing(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    await create_question(session, setup.a1, tier="foundation")

    first, second = await asyncio.gather(_next(client, setup), _next(client, setup))
    third = await _next(client, setup)

    assert first.json()["id"] == second.json()["id"] == third.json()["id"]


async def test_should_generate_on_the_spot_when_bank_empty(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    app.state.llm_client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(mcq()))
        .add(Verification, Reply(verification()))
    )

    response = await _next(client, setup)

    assert response.status_code == 200
    assert response.json()["stem"] == mcq().stem
    queued = await session.scalar(select(func.count()).select_from(Job))
    assert (queued or 0) >= 1  # bank top-up queued


async def test_empty_bank_without_claude_should_ask_to_wait_and_queue_generation(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    response = await _next(client, setup)

    assert response.status_code == 409
    assert error_code(response) == "QUESTIONS_PREPARING"
    keys = (await session.scalars(select(Job.dedupe_key))).all()
    assert f"gen:{setup.a1}:foundation:1" in keys


async def test_hints_should_reveal_one_at_a_time_up_to_four(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()

    revealed = [await _hint(client, item["id"]) for _ in range(5)]

    assert [r.status_code for r in revealed] == [200, 200, 200, 200, 409]
    assert revealed[3].json()["hints"] == ["Hint 1", "Hint 2", "Hint 3", "Hint 4"]
    assert revealed[3].json()["hintsRemaining"] == 0
    assert error_code(revealed[4]) == "NO_MORE_HINTS"


@pytest.mark.parametrize(
    ("question_type", "answer", "correct", "shown"),
    [
        ("multiple_choice", "c", True, "C: 6"),
        ("multiple_choice", "A", False, "C: 6"),
        ("numeric", "19/4 cm", True, "4.75 cm"),
        ("numeric", "4.7", False, "4.75 cm"),
        ("short_text", "Prime Number", True, "prime"),
    ],
)
async def test_answers_should_be_marked(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    question_type: str,
    answer: str,
    correct: bool,
    shown: str,
) -> None:
    await create_question(session, setup.a1, tier="foundation", question_type=question_type)
    item = (await _next(client, setup)).json()

    response = await _answer(client, item["id"], answer)

    assert response.status_code == 200
    body = response.json()
    assert (body["correct"], body["correctAnswer"], body["assisted"]) == (correct, shown, False)
    assert body["workedSolution"] == "The worked solution."


async def test_same_idempotency_key_should_replay_without_double_counting(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()

    first, retry = await asyncio.gather(
        _answer(client, item["id"], "C", key="key-12345678"),
        _answer(client, item["id"], "C", key="key-12345678"),
    )
    different = await _answer(client, item["id"], "C", key="key-87654321")

    progress = await session.get(ObjectiveProgress, (setup.student_id, setup.a1))
    assert first.json() == retry.json()
    assert different.status_code == 409
    assert error_code(different) == "ALREADY_ANSWERED"
    assert progress is not None
    assert progress.attempts == 1


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ({"answer": ""}, "valid-key-123"),
        ({"answer": "x" * 201}, "valid-key-123"),
        ({"answer": "C"}, "bad key!"),
        ({"answer": "C"}, None),
    ],
    ids=["empty", "too_long", "bad_key", "missing_key"],
)
async def test_invalid_answer_requests_should_be_rejected(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    body: dict[str, Any],
    key: str | None,
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()
    headers = {**csrf_headers(client), **({"Idempotency-Key": key} if key else {})}

    response = await client.post(
        f"/api/v1/practice/items/{item['id']}/answer", json=body, headers=headers
    )

    assert response.status_code == 422


async def test_three_correct_answers_should_move_up_a_level(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    for _ in range(3):
        await create_question(session, setup.a1, tier="foundation")
    await create_question(session, setup.a1, tier="foundation", difficulty=2, stem="Level two")

    levels = []
    for _ in range(3):
        item = (await _next(client, setup)).json()
        levels.append((await _answer(client, item["id"], "C")).json()["levelAfter"])
    next_item = (await _next(client, setup)).json()

    assert levels == [1, 1, 2]
    assert (next_item["difficulty"], next_item["stem"]) == (2, "Level two")


async def test_full_solution_should_mark_answer_assisted(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()
    for _ in range(4):
        await _hint(client, item["id"])

    result = (await _answer(client, item["id"], "C")).json()
    late_hint = await _hint(client, item["id"])

    assert (result["correct"], result["assisted"], result["levelAfter"]) == (True, True, 1)
    assert late_hint.status_code == 409
    assert error_code(late_hint) == "ALREADY_ANSWERED"


async def test_flag_should_hide_question_and_be_idempotent(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    question_id = await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()
    path = f"/api/v1/practice/items/{item['id']}/flag"

    responses = [
        await client.post(
            path, json={"reason": "Two answers look right"}, headers=csrf_headers(client)
        )
        for _ in range(2)
    ]
    after = await _next(client, setup)

    question = await session.get(Question, question_id)
    assert question is not None
    await session.refresh(question)
    assert [r.status_code for r in responses] == [204, 204]
    assert question.status is QuestionStatus.FLAGGED
    assert error_code(after) == "QUESTIONS_PREPARING"


async def test_other_students_item_should_be_not_found(
    client: httpx.AsyncClient, other_client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()
    await create_user(session, Role.STUDENT, identifier="other")
    await login(other_client, "other")

    responses = [
        await _answer(other_client, item["id"], "C"),
        await _hint(other_client, item["id"]),
    ]

    assert [r.status_code for r in responses] == [404, 404]


async def test_guardians_cannot_practise(
    other_client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_user(session, Role.GUARDIAN, identifier="parent@example.test")
    await login(other_client, "parent@example.test")

    response = await _next(other_client, setup)

    assert response.status_code == 403


async def test_practice_should_require_csrf(client: httpx.AsyncClient, setup: Setup) -> None:
    response = await client.post(setup.next_path())

    assert response.status_code == 403
    assert error_code(response) == "CSRF_FAILED"


@pytest.mark.parametrize(
    ("question_type", "answer", "keypad", "symbols"),
    [
        ("numeric", None, True, []),
        ("short_text", {"accepted": ["2:3"]}, True, list(KEYPAD_SYMBOLS)),
        ("short_text", None, False, list(KEYPAD_SYMBOLS)),
        ("multiple_choice", None, False, []),
    ],
)
async def test_should_offer_the_keys_the_answer_needs(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    question_type: str,
    answer: dict[str, object] | None,
    keypad: bool,
    symbols: list[str],
) -> None:
    # Arrange
    await create_question(
        session, setup.a1, tier="foundation", question_type=question_type, answer=answer
    )

    # Act
    body = (await _next(client, setup)).json()

    # Assert
    assert (body["keypad"], body["symbolKeys"]) == (keypad, symbols)


async def test_should_mark_a_typed_pi_answer_against_a_latex_key(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    await create_question(
        session,
        setup.a1,
        tier="foundation",
        question_type="short_text",
        answer={"accepted": [r"\frac{1}{2}\pi"]},
    )
    item = (await _next(client, setup)).json()

    # Act
    result = (await _answer(client, item["id"], "π/2")).json()

    # Assert
    assert "π" in item["symbolKeys"]
    assert result["correct"] is True
    assert result["correctAnswer"] == r"$\frac{1}{2}\pi$"
