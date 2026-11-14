# backend/tests/integration/test_subjects_api.py
"""Integration tests for the catalogue, the student's subject choice and topic map.

Covers:
- catalogue lists boards, subjects (with most common board) and current specs
  with set-text lists; requires sign-in
- setup: "I don't know" board -> most common board, unconfirmed; "not sure" tier
  -> Higher, unconfirmed; matching spec -> active; no spec for board -> pending
- set texts: listed option -> active; typed-in -> pending; option from another
  spec, unknown category -> 422
- typed-in subject -> pending with no board/spec
- validation: duplicate subject, unknown subject/board, tier on untiered -> 422
- idempotent re-save; removed subjects are deleted; board change re-matches spec
- concurrency: two simultaneous saves leave one consistent list
- setupCompleted flips on /users/me
- topic map: tier filters Higher-only statements; locked until taught;
  pending subject -> 409; another student's subject -> 404
- only students may use /me/subjects
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role
from tests.fixtures.factories import CurriculumIds, create_user, import_fixture_curriculum
from tests.integration.helpers import csrf_headers, error_code, login

pytestmark = pytest.mark.integration


@pytest.fixture
async def ids(session: AsyncSession) -> CurriculumIds:
    """The fixture curriculum, imported."""
    return await import_fixture_curriculum(session)


@pytest.fixture
async def student(client: httpx.AsyncClient, session: AsyncSession) -> httpx.AsyncClient:
    """A client signed in as a student."""
    await create_user(session, Role.STUDENT, identifier="sam10")
    assert (await login(client, "sam10")).status_code == 200
    return client


async def _save(client: httpx.AsyncClient, subjects: list[dict[str, Any]]) -> httpx.Response:
    return await client.put(
        "/api/v1/me/subjects", json={"subjects": subjects}, headers=csrf_headers(client)
    )


def _maths(ids: CurriculumIds, **extra: Any) -> dict[str, Any]:
    return {"subjectId": str(ids.subjects["maths"]), **extra}


async def test_catalogue_should_list_subjects_boards_and_current_specs(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await student.get("/api/v1/catalogue")

    assert response.status_code == 200
    body = response.json()
    assert [b["code"] for b in body["boards"]] == ["board-a", "board-b"]
    subjects = {s["slug"]: s for s in body["subjects"]}
    assert subjects["maths"]["mostCommonBoardId"] == str(ids.boards["board-a"])
    english = subjects["english-literature"]
    assert english["setTextCategories"] == ["Shakespeare play", "Poetry anthology cluster"]
    assert [t["title"] for t in english["specifications"][0]["setTexts"]] == [
        "Macbeth",
        "Romeo and Juliet",
        "Power and conflict",
    ]
    assert subjects["geography"]["specifications"] == []


async def test_catalogue_should_require_sign_in(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/catalogue")).status_code == 401


async def test_dont_know_board_and_tier_should_use_defaults_flagged_unconfirmed(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await _save(student, [_maths(ids)])

    assert response.status_code == 200
    [maths] = response.json()["subjects"]
    assert maths["boardId"] == str(ids.boards["board-a"])
    assert maths["boardName"] == "Board A"
    assert maths["boardConfirmed"] is False
    assert maths["tier"] == "higher"
    assert maths["tierConfirmed"] is False
    assert maths["status"] == "active"
    assert maths["specification"]["code"] == "M1"


async def test_board_without_imported_spec_should_be_pending(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await _save(
        student, [_maths(ids, boardId=str(ids.boards["board-b"]), tier="foundation")]
    )

    [maths] = response.json()["subjects"]
    assert maths["status"] == "pending"
    assert maths["specification"] is None
    assert (maths["boardConfirmed"], maths["tierConfirmed"]) == (True, True)


async def test_set_texts_from_list_are_active_and_typed_ones_pending(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    english = {
        "subjectId": str(ids.subjects["english-literature"]),
        "setTexts": [
            {"category": "Shakespeare play", "optionId": str(ids.set_texts["Macbeth"])},
            {"category": "Poetry anthology cluster", "customTitle": "Love and relationships"},
        ],
    }

    response = await _save(student, [english])

    [subject] = response.json()["subjects"]
    assert subject["status"] == "active"
    assert [(t["title"], t["status"]) for t in subject["setTexts"]] == [
        ("Macbeth", "active"),
        ("Love and relationships", "pending"),
    ]
    assert subject["setTexts"][0]["author"] == "William Shakespeare"


async def test_typed_in_subject_should_be_pending(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await _save(student, [{"customName": "Statistics"}])

    [subject] = response.json()["subjects"]
    assert subject["subjectName"] == "Statistics"
    assert subject["isCustom"] is True
    assert subject["status"] == "pending"
    assert subject["boardId"] is None


@pytest.mark.parametrize(
    "build",
    [
        lambda ids: [_maths(ids), _maths(ids)],
        lambda ids: [{"subjectId": "00000000-0000-0000-0000-000000000000"}],
        lambda ids: [_maths(ids, boardId="00000000-0000-0000-0000-000000000000")],
        lambda ids: [{"subjectId": str(ids.subjects["geography"]), "tier": "higher"}],
        lambda ids: [
            {
                "subjectId": str(ids.subjects["english-literature"]),
                "setTexts": [{"category": "Sci-fi", "customTitle": "Dune"}],
            }
        ],
        lambda ids: [
            {
                "subjectId": str(ids.subjects["english-literature"]),
                "boardId": str(ids.boards["board-a"]),
                "setTexts": [
                    {"category": "Shakespeare play", "optionId": str(ids.set_texts["Macbeth"])}
                ],
            }
        ],
        lambda ids: [{"customName": "Art"}, {"customName": " art "}],
    ],
    ids=[
        "duplicate_subject",
        "unknown_subject",
        "unknown_board",
        "tier_on_untiered",
        "unknown_category",
        "option_not_on_this_spec",
        "duplicate_custom_name",
    ],
)
async def test_should_reject_invalid_choices(
    student: httpx.AsyncClient, ids: CurriculumIds, build: Any
) -> None:
    response = await _save(student, build(ids))

    assert response.status_code == 422


async def test_should_reject_choice_with_both_subject_and_custom_name(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await _save(student, [_maths(ids, customName="Maths")])

    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"


async def test_resave_should_be_idempotent_and_remove_dropped_subjects(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    geography = {"subjectId": str(ids.subjects["geography"])}
    first = (await _save(student, [_maths(ids), geography])).json()["subjects"]

    second = (await _save(student, [_maths(ids), geography])).json()["subjects"]
    third = (await _save(student, [geography])).json()["subjects"]

    assert [s["id"] for s in second] == [s["id"] for s in first]
    assert [s["subjectName"] for s in third] == ["Geography"]


async def test_changing_board_should_rematch_specification(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    await _save(student, [_maths(ids, boardId=str(ids.boards["board-a"]))])

    response = await _save(student, [_maths(ids, boardId=str(ids.boards["board-b"]))])

    [maths] = response.json()["subjects"]
    assert maths["status"] == "pending"


async def test_concurrent_saves_should_leave_one_consistent_list(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    subjects = [_maths(ids), {"subjectId": str(ids.subjects["geography"])}]

    first, second = await asyncio.gather(_save(student, subjects), _save(student, subjects))

    assert (first.status_code, second.status_code) == (200, 200)
    listed = (await student.get("/api/v1/me/subjects")).json()["subjects"]
    assert len(listed) == 2


async def test_setup_should_mark_user_as_set_up(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    before = (await student.get("/api/v1/users/me")).json()["setupCompleted"]

    await _save(student, [_maths(ids)])

    after = (await student.get("/api/v1/users/me")).json()["setupCompleted"]
    mine = (await student.get("/api/v1/me/subjects")).json()
    assert (before, after, mine["setupCompleted"]) == (False, True, True)


@pytest.mark.parametrize(("tier", "counts"), [("foundation", [2, 1]), ("higher", [3, 1])])
async def test_topic_map_should_count_only_statements_on_students_tier(
    student: httpx.AsyncClient, ids: CurriculumIds, tier: str, counts: list[int]
) -> None:
    [maths] = (await _save(student, [_maths(ids, tier=tier)])).json()["subjects"]

    response = await student.get(f"/api/v1/me/subjects/{maths['id']}/topics")

    assert response.status_code == 200
    topics = response.json()["topics"]
    assert [t["title"] for t in topics] == ["Number", "Algebra"]
    assert [t["subtopics"][0]["objectiveCount"] for t in topics] == counts
    assert all(t["unlocked"] is False for t in topics)


async def test_topic_map_should_409_for_pending_subject(
    student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [pending] = (await _save(student, [{"customName": "Statistics"}])).json()["subjects"]

    response = await student.get(f"/api/v1/me/subjects/{pending['id']}/topics")

    assert response.status_code == 409
    assert error_code(response) == "SUBJECT_NOT_READY"


async def test_student_should_not_see_another_students_topic_map(
    student: httpx.AsyncClient,
    other_client: httpx.AsyncClient,
    session: AsyncSession,
    ids: CurriculumIds,
) -> None:
    [maths] = (await _save(student, [_maths(ids)])).json()["subjects"]
    await create_user(session, Role.STUDENT, identifier="other")
    await login(other_client, "other")

    response = await other_client.get(f"/api/v1/me/subjects/{maths['id']}/topics")

    assert response.status_code == 404


async def test_only_students_may_choose_subjects(
    client: httpx.AsyncClient, session: AsyncSession, ids: CurriculumIds
) -> None:
    await create_user(session, Role.GUARDIAN, identifier="parent@example.test")
    await login(client, "parent@example.test")

    response = await _save(client, [_maths(ids)])

    assert response.status_code == 403
