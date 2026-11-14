# backend/tests/integration/test_admin_curriculum_api.py
"""Integration tests for the admin's curriculum and enrolment tools.

Covers:
- specification list with topic/objective counts
- enrolment list: attention filter (no spec / unconfirmed board or tier /
  pending set text) and cursor pagination; invalid cursor -> 422
- confirming board/tier clears attention; changing board re-matches spec
- choosing a spec for a typed-in subject converts it; duplicate -> 409;
  spec for another subject/board -> 422; unknown ids -> 404
- matching a typed-in set text to an option; option from another spec -> 422;
  deleting a set text is idempotent
- taught-at-school toggle unlocks the topic for the student; topic order must
  list every topic exactly once
- every admin endpoint is forbidden to students
"""

from __future__ import annotations

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
async def student(other_client: httpx.AsyncClient, session: AsyncSession) -> httpx.AsyncClient:
    """A signed-in student (separate browser from the admin)."""
    await create_user(session, Role.STUDENT, identifier="sam10")
    assert (await login(other_client, "sam10")).status_code == 200
    return other_client


@pytest.fixture
async def admin(client: httpx.AsyncClient, session: AsyncSession) -> httpx.AsyncClient:
    """A signed-in admin."""
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    assert (await login(client, "admin@example.test")).status_code == 200
    return client


async def _choose(
    student: httpx.AsyncClient, subjects: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    response = await student.put(
        "/api/v1/me/subjects", json={"subjects": subjects}, headers=csrf_headers(student)
    )
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()["subjects"]
    return result


async def _patch(admin: httpx.AsyncClient, path: str, body: dict[str, Any]) -> httpx.Response:
    return await admin.patch(path, json=body, headers=csrf_headers(admin))


async def test_should_list_specifications_with_counts(
    admin: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    response = await admin.get("/api/v1/admin/specifications")

    assert response.status_code == 200
    specs = {s["code"]: s for s in response.json()}
    assert (specs["M1"]["topicCount"], specs["M1"]["objectiveCount"]) == (2, 4)
    assert specs["M1"]["boardName"] == "Board A"
    assert specs["L1"]["isCurrent"] is True


async def test_attention_filter_should_list_only_enrolments_needing_admin(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    await _choose(
        student,
        [
            {"subjectId": str(ids.subjects["maths"])},  # board + tier unconfirmed
            {
                "subjectId": str(ids.subjects["english-literature"]),
                "boardId": str(ids.boards["board-b"]),
            },
            {"customName": "Statistics"},  # no spec
        ],
    )

    everything = (await admin.get("/api/v1/admin/enrolments")).json()["items"]
    attention = (await admin.get("/api/v1/admin/enrolments?attention=true")).json()["items"]

    assert len(everything) == 3
    reasons = {e["subjectName"]: e["attention"] for e in attention}
    assert reasons == {
        "Mathematics": ["board_unconfirmed", "tier_unconfirmed"],
        "Statistics": ["no_specification", "board_unconfirmed", "tier_unconfirmed"],
    }
    assert attention[0]["studentName"] == "Sam"


async def test_enrolment_list_should_paginate_with_cursor(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    await _choose(student, [{"customName": f"Subject {i}"} for i in range(3)])

    first = (await admin.get("/api/v1/admin/enrolments?limit=2")).json()
    second = (
        await admin.get(f"/api/v1/admin/enrolments?limit=2&cursor={first['nextCursor']}")
    ).json()

    names = [e["subjectName"] for e in first["items"] + second["items"]]
    assert sorted(names) == ["Subject 0", "Subject 1", "Subject 2"]
    assert second["nextCursor"] is None


async def test_invalid_cursor_should_be_rejected(admin: httpx.AsyncClient) -> None:
    response = await admin.get("/api/v1/admin/enrolments?cursor=not-a-cursor")

    assert response.status_code == 422
    assert error_code(response) == "INVALID_CURSOR"


async def test_confirming_board_and_tier_should_clear_attention(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])

    response = await _patch(
        admin,
        f"/api/v1/admin/enrolments/{maths['id']}",
        {"boardId": str(ids.boards["board-a"]), "tier": "foundation"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attention"] == []
    assert (body["tier"], body["status"]) == ("foundation", "active")


async def test_changing_board_should_rematch_spec(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])

    response = await _patch(
        admin, f"/api/v1/admin/enrolments/{maths['id']}", {"boardId": str(ids.boards["board-b"])}
    )

    assert response.json()["status"] == "pending"


async def test_choosing_spec_should_convert_typed_in_subject(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [custom] = await _choose(student, [{"customName": "Maths (further)"}])

    response = await _patch(
        admin, f"/api/v1/admin/enrolments/{custom['id']}", {"specificationId": str(ids.specs["M1"])}
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["subjectName"], body["isCustom"], body["status"]) == (
        "Mathematics",
        False,
        "active",
    )
    assert body["boardConfirmed"] is True


async def test_converting_to_a_subject_already_chosen_should_conflict(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    _, custom = await _choose(
        student, [{"subjectId": str(ids.subjects["maths"])}, {"customName": "More maths"}]
    )

    response = await _patch(
        admin, f"/api/v1/admin/enrolments/{custom['id']}", {"specificationId": str(ids.specs["M1"])}
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (lambda ids: {"specificationId": str(ids.specs["L1"])}, 422),
        (
            lambda ids: {
                "specificationId": str(ids.specs["M1"]),
                "boardId": str(ids.boards["board-b"]),
            },
            422,
        ),
        (lambda ids: {"specificationId": "00000000-0000-0000-0000-000000000000"}, 404),
        (lambda ids: {"boardId": "00000000-0000-0000-0000-000000000000"}, 404),
        (lambda ids: {}, 422),
    ],
    ids=["other_subject", "other_board", "unknown_spec", "unknown_board", "empty"],
)
async def test_invalid_enrolment_updates_should_be_rejected(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds, body: Any, status: int
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])

    response = await _patch(admin, f"/api/v1/admin/enrolments/{maths['id']}", body(ids))

    assert response.status_code == status


async def test_unknown_enrolment_should_404(admin: httpx.AsyncClient) -> None:
    response = await _patch(
        admin, "/api/v1/admin/enrolments/00000000-0000-0000-0000-000000000000", {"tier": "higher"}
    )

    assert response.status_code == 404


async def test_should_match_typed_set_text_and_delete_idempotently(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    # Arrange
    [english] = await _choose(
        student,
        [
            {
                "subjectId": str(ids.subjects["english-literature"]),
                "boardId": str(ids.boards["board-b"]),
                "setTexts": [
                    {"category": "Shakespeare play", "customTitle": "Romeo & Juliet"},
                    {"category": "Shakespeare play", "customTitle": "Typo"},
                ],
            }
        ],
    )
    romeo, typo = english["setTexts"]

    # Act
    matched = await _patch(
        admin,
        f"/api/v1/admin/set-texts/{romeo['id']}",
        {"optionId": str(ids.set_texts["Romeo and Juliet"])},
    )
    deletes = [
        await admin.delete(f"/api/v1/admin/set-texts/{typo['id']}", headers=csrf_headers(admin))
        for _ in range(2)
    ]

    # Assert
    assert matched.status_code == 200
    assert [(t["title"], t["status"]) for t in matched.json()["setTexts"]] == [
        ("Romeo and Juliet", "active"),
        ("Typo", "pending"),
    ]
    assert [d.status_code for d in deletes] == [204, 204]
    mine = (await student.get("/api/v1/me/subjects")).json()["subjects"][0]
    assert [t["title"] for t in mine["setTexts"]] == ["Romeo and Juliet"]


async def test_matching_option_from_another_spec_should_be_rejected(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [english] = await _choose(
        student,
        [
            {
                "subjectId": str(ids.subjects["english-literature"]),
                "boardId": str(ids.boards["board-a"]),  # no spec on board A
                "setTexts": [{"category": "Shakespeare play", "customTitle": "Macbeth"}],
            }
        ],
    )

    response = await _patch(
        admin,
        f"/api/v1/admin/set-texts/{english['setTexts'][0]['id']}",
        {"optionId": str(ids.set_texts["Macbeth"])},
    )

    assert response.status_code == 422


async def test_taught_toggle_should_unlock_topic_for_student(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])
    topic_id = ids.topics["M1:2"]

    response = await admin.put(
        f"/api/v1/admin/enrolments/{maths['id']}/topics/{topic_id}",
        json={"taughtAtSchool": True},
        headers=csrf_headers(admin),
    )

    assert response.status_code == 200
    student_view = (await student.get(f"/api/v1/me/subjects/{maths['id']}/topics")).json()
    assert {t["title"]: t["unlocked"] for t in student_view["topics"]} == {
        "Number": False,
        "Algebra": True,
    }


async def test_topic_from_another_spec_should_404(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])

    response = await admin.put(
        f"/api/v1/admin/enrolments/{maths['id']}/topics/{ids.topics['L1:1']}",
        json={"taughtAtSchool": True},
        headers=csrf_headers(admin),
    )

    assert response.status_code == 404


async def test_topic_order_should_reorder_and_require_every_topic(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [maths] = await _choose(student, [{"subjectId": str(ids.subjects["maths"])}])
    path = f"/api/v1/admin/enrolments/{maths['id']}/topic-order"
    algebra, number = str(ids.topics["M1:2"]), str(ids.topics["M1:1"])

    ok = await admin.put(path, json={"topicIds": [algebra, number]}, headers=csrf_headers(admin))
    partial = await admin.put(path, json={"topicIds": [algebra]}, headers=csrf_headers(admin))
    repeated = await admin.put(
        path, json={"topicIds": [algebra, algebra]}, headers=csrf_headers(admin)
    )

    assert [t["title"] for t in ok.json()["topics"]] == ["Algebra", "Number"]
    assert (partial.status_code, repeated.status_code) == (422, 422)
    student_view = (await student.get(f"/api/v1/me/subjects/{maths['id']}/topics")).json()
    assert [t["title"] for t in student_view["topics"]] == ["Algebra", "Number"]


async def test_topic_order_should_409_for_pending_subject(
    admin: httpx.AsyncClient, student: httpx.AsyncClient, ids: CurriculumIds
) -> None:
    [custom] = await _choose(student, [{"customName": "Statistics"}])

    response = await admin.put(
        f"/api/v1/admin/enrolments/{custom['id']}/topic-order",
        json={"topicIds": [str(ids.topics["M1:1"])]},
        headers=csrf_headers(admin),
    )
    topics = await admin.get(f"/api/v1/admin/enrolments/{custom['id']}/topics")

    assert response.status_code == 409
    assert topics.status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/admin/specifications"),
        ("GET", "/api/v1/admin/enrolments"),
        ("PATCH", "/api/v1/admin/enrolments/00000000-0000-0000-0000-000000000000"),
        ("PATCH", "/api/v1/admin/set-texts/00000000-0000-0000-0000-000000000000"),
    ],
)
async def test_admin_endpoints_should_be_forbidden_to_students(
    student: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await student.request(
        method,
        path,
        json={"tier": "higher", "optionId": "00000000-0000-0000-0000-000000000000"},
        headers=csrf_headers(student),
    )

    assert response.status_code == 403
