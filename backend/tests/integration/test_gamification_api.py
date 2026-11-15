# backend/tests/integration/test_gamification_api.py
"""Integration tests for XP, streaks, badges, the dashboard, challenges and boss battles.

Covers:
- answers earn XP (10 per difficulty), wrong answers none; a replayed answer
  returns the same rewards and adds no XP; level up reported; streak counts
  London days and extends the next day; a streak reaching 5 grants the badge
  once, listed by /me/badges
- dashboard: new student (level 1, no streak, Continue → first unlocked topic);
  with a review due Continue → review; with today's challenge started
  Continue → daily
- daily challenge: one per day (repeat returns it); mixes skills across
  unlocked topics; includes a due review first; answering the last question
  completes it with the 50 XP bonus (reported with that answer) and results;
  "next" afterwards → 409 CHALLENGE_FINISHED; no unlocked topics → 409
  NOTHING_TO_PRACTISE; no questions → 409 QUESTIONS_PREPARING with generation
  queued; challenge items don't leak into topic practice
- boss battle: locked until half the topic is practised (409 BOSS_LOCKED, and
  the topic map says so); starting twice returns the same battle; timed; no
  hints (409 HINTS_OFF); doesn't move the ladder; finishing early scores
  answered questions only, adds the bonus and a percentage-only estimate;
  personal best on the next battle; time up → 409 TIME_UP and scored; with
  admin grade boundaries the result has a grade band; rings on topic map and
  progress
- grade boundaries (admin): replace and list; grade outside the tier, repeated
  grade or falling percentages → 422; students → 403
- access: another student's challenge → 404; daily on a locked topic only;
  guardians → 403
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curriculum import LearningObjective
from app.models.enrolment import StudentTopicSetting
from app.models.gamification import Streak, XpEvent, XpSource
from app.models.ops import Job
from app.models.question import ObjectiveProgress
from app.models.user import Role
from app.practice.review import london_today
from tests.fixtures.factories import FakeClock, create_question, create_user
from tests.integration.helpers import csrf_headers, error_code, login, refresh
from tests.integration.test_practice_api import Setup, _answer, _hint, _next, setup

pytestmark = pytest.mark.integration
__all__ = ["setup"]  # re-exported fixture

RIGHT, WRONG = "C", "A"  # the factory's multiple-choice key is C


async def _post(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.post(f"/api/v1{path}", headers=csrf_headers(client))


async def _dashboard(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/v1/me/dashboard")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def _later(client: httpx.AsyncClient, clock: FakeClock, **delta: float) -> None:
    clock.advance(**delta)
    assert (await refresh(client)).status_code == 200


async def _objective(session: AsyncSession, ref: str) -> uuid.UUID:
    objective_id = await session.scalar(
        select(LearningObjective.id).where(LearningObjective.ref == ref)
    )
    assert objective_id is not None
    return objective_id


async def _unlock_number(session: AsyncSession, setup: Setup) -> tuple[uuid.UUID, uuid.UUID]:
    """Also cover topic 1 (Number: T1, T2 on Foundation); returns their IDs."""
    session.add(
        StudentTopicSetting(
            student_id=setup.student_id, topic_id=setup.number, taught_at_school=True
        )
    )
    await session.commit()
    return await _objective(session, "T1"), await _objective(session, "T2")


async def _answer_all(
    client: httpx.AsyncClient, challenge_id: str, answer: str
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    while True:
        item = await _post(client, f"/practice/challenges/{challenge_id}/next")
        if item.status_code != 200:
            assert error_code(item) == "CHALLENGE_FINISHED"
            return results
        results.append((await _answer(client, item.json()["id"], answer)).json())


# --------------------------------------------------------------------- XP, levels, streaks


async def test_answers_should_earn_xp_by_difficulty_and_count_the_streak(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    for _ in range(2):
        await create_question(session, setup.a1, tier="foundation")

    # Act
    right = (await _answer(client, (await _next(client, setup)).json()["id"], RIGHT)).json()
    wrong = (await _answer(client, (await _next(client, setup)).json()["id"], WRONG)).json()

    # Assert
    assert right["rewards"]["xpGained"] == 10
    assert (right["rewards"]["streakDays"], right["rewards"]["streakExtended"]) == (1, True)
    assert wrong["rewards"]["xpGained"] == 0
    assert (wrong["rewards"]["totalXp"], wrong["rewards"]["streakExtended"]) == (10, False)


async def test_replayed_answer_should_not_add_xp_twice(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    await create_question(session, setup.a1, tier="foundation")
    item = (await _next(client, setup)).json()

    # Act
    first = (await _answer(client, item["id"], RIGHT, key="same-key-123")).json()
    again = (await _answer(client, item["id"], RIGHT, key="same-key-123")).json()

    # Assert
    assert first["rewards"] == again["rewards"]
    count = await session.scalar(select(func.count()).select_from(XpEvent))
    assert count == 1


async def test_should_report_a_level_up(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange: 95 XP already
    session.add(
        XpEvent(
            user_id=setup.student_id,
            source=XpSource.ANSWER,
            ref_id=uuid.uuid4(),
            amount=95,
            created_at=clock.now(),
        )
    )
    await session.commit()
    await create_question(session, setup.a1, tier="foundation")

    # Act
    rewards = (await _answer(client, (await _next(client, setup)).json()["id"], RIGHT)).json()[
        "rewards"
    ]

    # Assert
    assert (rewards["level"], rewards["levelUp"], rewards["xpIntoLevel"]) == (2, True, 5)


async def test_streak_should_extend_the_next_london_day(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange
    for _ in range(2):
        await create_question(session, setup.a1, tier="foundation")
    await _answer(client, (await _next(client, setup)).json()["id"], RIGHT)
    await _later(client, clock, days=1)

    # Act
    rewards = (await _answer(client, (await _next(client, setup)).json()["id"], RIGHT)).json()[
        "rewards"
    ]

    # Assert
    assert (rewards["streakDays"], rewards["streakExtended"]) == (2, True)


async def test_five_day_streak_should_grant_its_badge_once(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange: active for the last four days
    yesterday = london_today(clock.now()) - timedelta(days=1)
    session.add(
        Streak(user_id=setup.student_id, current_days=4, longest_days=4, last_active_on=yesterday)
    )
    await session.commit()
    for _ in range(2):
        await create_question(session, setup.a1, tier="foundation")

    # Act
    first = (await _answer(client, (await _next(client, setup)).json()["id"], WRONG)).json()
    second = (await _answer(client, (await _next(client, setup)).json()["id"], RIGHT)).json()
    badges = (await client.get("/api/v1/me/badges")).json()

    # Assert
    assert [b["code"] for b in first["rewards"]["newBadges"]] == ["streak_5"]
    assert second["rewards"]["newBadges"] == []
    earned = {b["code"] for b in badges if b["earnedAt"]}
    assert earned == {"streak_5"}
    assert len(badges) == 10


# --------------------------------------------------------------------- dashboard


async def test_new_student_dashboard_should_continue_to_the_first_topic(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    # Act
    body = await _dashboard(client)

    # Assert
    assert body["level"] == {"level": 1, "totalXp": 0, "xpIntoLevel": 0, "xpForLevel": 100}
    assert body["streak"]["currentDays"] == 0
    assert body["streak"]["freezeAvailable"] is True
    assert body["daily"]["status"] == "not_started"
    assert body["continueTo"]["kind"] == "topic"
    assert body["continueTo"]["topicId"] == str(setup.number)
    assert (body["badgesEarned"], body["badgesTotal"]) == (0, 10)


async def test_dashboard_should_continue_to_reviews_then_todays_challenge(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange: a mistake, due tomorrow
    for _ in range(3):
        await create_question(session, setup.a1, tier="foundation")
    await _answer(client, (await _next(client, setup)).json()["id"], WRONG)
    await _later(client, clock, days=1)

    # Act / Assert: review first
    body = await _dashboard(client)
    assert (body["continueTo"]["kind"], body["reviewsDue"]) == ("review", 1)

    # Act / Assert: once today's challenge is started, carry on with it
    challenge = (await _post(client, "/practice/challenges/daily")).json()
    body = await _dashboard(client)
    assert body["continueTo"] == {
        "kind": "daily",
        "challengeId": challenge["id"],
        "enrolmentId": None,
        "topicId": None,
        "label": "Carry on with today's challenge",
    }
    assert body["daily"]["status"] == "active"


# --------------------------------------------------------------------- daily challenge


async def test_daily_challenge_should_mix_skills_complete_and_pay_its_bonus(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    t1, t2 = await _unlock_number(session, setup)
    for objective in (t1, t2, setup.a1):
        await create_question(session, objective, tier="foundation")

    # Act
    started = await _post(client, "/practice/challenges/daily")
    again = await _post(client, "/practice/challenges/daily")
    results = await _answer_all(client, started.json()["id"], RIGHT)
    finished = (await client.get(f"/api/v1/practice/challenges/{started.json()['id']}")).json()

    # Assert
    assert started.status_code == 200
    assert again.json()["id"] == started.json()["id"]
    assert started.json()["total"] == 3
    assert [r["challenge"]["answered"] for r in results] == [1, 2, 3]
    last = results[-1]
    assert last["challenge"]["completed"] is True
    assert last["rewards"]["bonusXp"] == 50
    assert last["rewards"]["totalXp"] == 30 + 50
    assert (finished["status"], finished["score"], finished["maxScore"]) == ("completed", 3, 3)
    assert finished["bonusXp"] == 50
    assert [r["position"] for r in finished["results"]] == [1, 2, 3]
    assert (await _dashboard(client))["daily"]["status"] == "completed"


async def test_daily_challenge_should_start_with_a_due_review(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange
    for _ in range(3):
        await create_question(session, setup.a1, tier="foundation")
    await _answer(client, (await _next(client, setup)).json()["id"], WRONG)
    await _later(client, clock, days=1)

    # Act
    challenge = (await _post(client, "/practice/challenges/daily")).json()
    first = (await _post(client, f"/practice/challenges/{challenge['id']}/next")).json()

    # Assert
    assert first["review"] is True
    assert challenge["total"] == 2


async def test_challenge_items_should_not_leak_into_topic_practice(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    for _ in range(2):
        await create_question(session, setup.a1, tier="foundation")
    challenge = (await _post(client, "/practice/challenges/daily")).json()
    challenge_item = (await _post(client, f"/practice/challenges/{challenge['id']}/next")).json()

    # Act
    practice_item = (await _next(client, setup)).json()

    # Assert
    assert practice_item["id"] != challenge_item["id"]


async def test_daily_challenge_should_need_an_unlocked_topic(
    client: httpx.AsyncClient, session: AsyncSession, other_client: httpx.AsyncClient
) -> None:
    # Arrange: a student with no subjects
    await create_user(session, Role.STUDENT, identifier="newbie")
    assert (await login(other_client, "newbie")).status_code == 200

    # Act
    response = await _post(other_client, "/practice/challenges/daily")

    # Assert
    assert response.status_code == 409
    assert error_code(response) == "NOTHING_TO_PRACTISE"


async def test_daily_challenge_without_questions_should_queue_generation(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Act
    response = await _post(client, "/practice/challenges/daily")

    # Assert
    assert response.status_code == 409
    assert error_code(response) == "QUESTIONS_PREPARING"
    jobs = await session.scalar(select(func.count()).select_from(Job))
    assert jobs is not None
    assert jobs >= 1


# --------------------------------------------------------------------- boss battles


async def _ready_for_boss(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Practise one of topic 1's two skills (half the topic); returns the boss path."""
    t1, t2 = await _unlock_number(session, setup)
    await create_question(session, t1, tier="foundation")
    item = (await _next(client, setup, setup.number)).json()
    await _answer(client, item["id"], RIGHT)
    for objective in (t1, t2):
        await create_question(session, objective, tier="foundation", difficulty=3)
    return f"/practice/enrolments/{setup.enrolment_id}/topics/{setup.number}/boss", t1, t2


async def test_boss_battle_should_unlock_after_half_the_topic(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    _t1, _ = await _unlock_number(session, setup)
    path = f"/practice/enrolments/{setup.enrolment_id}/topics/{setup.number}/boss"

    # Act
    locked = await _post(client, path)
    topic_map = (await client.get(f"/api/v1/me/subjects/{setup.enrolment_id}/topics")).json()

    # Assert
    assert locked.status_code == 409
    assert error_code(locked) == "BOSS_LOCKED"
    number = next(t for t in topic_map["topics"] if t["id"] == str(setup.number))
    assert number["standing"]["bossUnlocked"] is False
    assert number["standing"]["skillsToUnlockBoss"] == 1


async def test_boss_battle_should_be_timed_hintless_and_scored_when_finished(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    path, t1, _ = await _ready_for_boss(client, session, setup)
    level_before = (await session.get(ObjectiveProgress, (setup.student_id, t1))).level  # type: ignore[union-attr]

    # Act
    boss = (await _post(client, path)).json()
    again = (await _post(client, path)).json()
    item = (await _post(client, f"/practice/challenges/{boss['id']}/next")).json()
    hint = await _hint(client, item["id"])
    answered = (await _answer(client, item["id"], RIGHT)).json()
    finished = (await _post(client, f"/practice/challenges/{boss['id']}/finish")).json()
    finished_again = await _post(client, f"/practice/challenges/{boss['id']}/finish")

    # Assert
    assert again["id"] == boss["id"]
    assert (boss["kind"], boss["total"], boss["secondsLeft"]) == ("boss", 2, 300)
    assert boss["topicTitle"]
    assert hint.status_code == 409
    assert error_code(hint) == "HINTS_OFF"
    assert answered["challenge"]["completed"] is False
    assert (finished["score"], finished["maxScore"], finished["percent"]) == (1, 2, 50.0)
    assert finished["bonusXp"] == 60
    assert finished["grade"] == {
        "percent": 50.0,
        "standing": "developing",
        "bandLow": None,
        "bandHigh": None,
        "belowLowestGrade": None,
    }
    assert (finished["previousBest"], finished["personalBest"]) == (None, True)
    assert [r["answered"] for r in finished["results"]] == [True, False]
    assert finished_again.json()["bonusXp"] == 60
    await session.close()
    progress = await session.get(ObjectiveProgress, (setup.student_id, t1))
    assert progress is not None
    assert progress.level == level_before


async def test_boss_battle_should_track_personal_bests(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange: a first battle at 0%
    path, *_ = await _ready_for_boss(client, session, setup)
    first = (await _post(client, path)).json()
    await _post(client, f"/practice/challenges/{first['id']}/finish")

    # Act: a second battle, all right
    second = (await _post(client, path)).json()
    await _answer_all(client, second["id"], RIGHT)
    result = (await client.get(f"/api/v1/practice/challenges/{second['id']}")).json()

    # Assert
    assert second["id"] != first["id"]
    assert (result["percent"], result["previousBest"], result["personalBest"]) == (
        100.0,
        0.0,
        True,
    )


async def test_boss_battle_should_refuse_answers_after_time_up(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup, clock: FakeClock
) -> None:
    # Arrange
    path, *_ = await _ready_for_boss(client, session, setup)
    boss = (await _post(client, path)).json()
    item = (await _post(client, f"/practice/challenges/{boss['id']}/next")).json()
    await _later(client, clock, minutes=6)

    # Act
    late = await _answer(client, item["id"], RIGHT)
    state = (await client.get(f"/api/v1/practice/challenges/{boss['id']}")).json()
    next_item = await _post(client, f"/practice/challenges/{boss['id']}/next")

    # Assert
    assert late.status_code == 409
    assert error_code(late) == "TIME_UP"
    assert (state["status"], state["percent"]) == ("completed", 0.0)
    assert error_code(next_item) == "CHALLENGE_FINISHED"


async def test_boss_result_should_show_a_grade_band_once_boundaries_exist(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    other_client: httpx.AsyncClient,
) -> None:
    # Arrange: admin enters Foundation boundaries
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    assert (await login(other_client, "admin@example.test")).status_code == 200
    spec_id = setup.ids.specs["M1"]
    put = await other_client.put(
        f"/api/v1/admin/specifications/{spec_id}/grade-boundaries",
        json={
            "tier": "foundation",
            "boundaries": [
                {"grade": 1, "minPercent": 15},
                {"grade": 3, "minPercent": 45},
                {"grade": 2, "minPercent": 30},
                {"grade": 4, "minPercent": 60},
                {"grade": 5, "minPercent": 75},
            ],
        },
        headers=csrf_headers(other_client),
    )
    path, *_ = await _ready_for_boss(client, session, setup)
    boss = (await _post(client, path)).json()
    item = (await _post(client, f"/practice/challenges/{boss['id']}/next")).json()
    await _answer(client, item["id"], RIGHT)

    # Act
    result = (await _post(client, f"/practice/challenges/{boss['id']}/finish")).json()
    listed = (
        await other_client.get(f"/api/v1/admin/specifications/{spec_id}/grade-boundaries")
    ).json()

    # Assert
    assert put.status_code == 200
    assert [b["grade"] for b in put.json()["boundaries"]] == [1, 2, 3, 4, 5]
    assert [b["minPercent"] for b in listed[0]["boundaries"]] == [15, 30, 45, 60, 75]
    assert (result["grade"]["bandLow"], result["grade"]["bandHigh"]) == (3, 4)


@pytest.mark.parametrize(
    "boundaries",
    [
        [{"grade": 7, "minPercent": 60}],  # Foundation tops out at 5
        [{"grade": 4, "minPercent": 60}, {"grade": 4, "minPercent": 70}],
        [{"grade": 4, "minPercent": 60}, {"grade": 5, "minPercent": 50}],
    ],
)
async def test_grade_boundaries_should_be_validated(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    other_client: httpx.AsyncClient,
    boundaries: list[dict[str, Any]],
) -> None:
    # Arrange
    await create_user(session, Role.ADMIN, identifier="admin@example.test")
    assert (await login(other_client, "admin@example.test")).status_code == 200

    # Act
    response = await other_client.put(
        f"/api/v1/admin/specifications/{setup.ids.specs['M1']}/grade-boundaries",
        json={"tier": "foundation", "boundaries": boundaries},
        headers=csrf_headers(other_client),
    )

    # Assert
    assert response.status_code == 422


async def test_students_should_not_edit_grade_boundaries(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    response = await client.put(
        f"/api/v1/admin/specifications/{setup.ids.specs['M1']}/grade-boundaries",
        json={"tier": "foundation", "boundaries": []},
        headers=csrf_headers(client),
    )
    assert response.status_code == 403


async def test_rings_should_show_on_the_topic_map_and_progress(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    # Arrange
    path, *_ = await _ready_for_boss(client, session, setup)

    # Act
    topic_map = (await client.get(f"/api/v1/me/subjects/{setup.enrolment_id}/topics")).json()
    progress = (await client.get(f"/api/v1/me/subjects/{setup.enrolment_id}/progress")).json()

    # Assert
    number = next(t for t in topic_map["topics"] if t["id"] == str(setup.number))
    assert number["standing"]["bossUnlocked"] is True
    assert number["standing"]["ring"] in {"none", "bronze"}
    assert all("ring" in t for t in progress["topics"])
    assert path


# --------------------------------------------------------------------- access


async def test_another_students_challenge_should_be_hidden(
    client: httpx.AsyncClient,
    session: AsyncSession,
    setup: Setup,
    other_client: httpx.AsyncClient,
) -> None:
    # Arrange
    await create_question(session, setup.a1, tier="foundation")
    challenge = (await _post(client, "/practice/challenges/daily")).json()
    await create_user(session, Role.STUDENT, identifier="someone")
    assert (await login(other_client, "someone")).status_code == 200

    # Act
    responses = [
        await other_client.get(f"/api/v1/practice/challenges/{challenge['id']}"),
        await _post(other_client, f"/practice/challenges/{challenge['id']}/next"),
        await _post(other_client, f"/practice/challenges/{challenge['id']}/finish"),
    ]

    # Assert
    assert [r.status_code for r in responses] == [404, 404, 404]


async def test_daily_challenge_cannot_be_ended_early(
    client: httpx.AsyncClient, session: AsyncSession, setup: Setup
) -> None:
    await create_question(session, setup.a1, tier="foundation")
    challenge = (await _post(client, "/practice/challenges/daily")).json()
    response = await _post(client, f"/practice/challenges/{challenge['id']}/finish")
    assert error_code(response) == "NOT_A_BOSS_BATTLE"


async def test_guardians_should_not_reach_student_gamification(
    client: httpx.AsyncClient, session: AsyncSession, other_client: httpx.AsyncClient
) -> None:
    await create_user(session, Role.GUARDIAN, identifier="parent@example.test")
    assert (await login(other_client, "parent@example.test")).status_code == 200
    assert (await other_client.get("/api/v1/me/dashboard")).status_code == 403
    assert (await _post(other_client, "/practice/challenges/daily")).status_code == 403
