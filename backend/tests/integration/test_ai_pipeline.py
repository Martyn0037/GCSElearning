# backend/tests/integration/test_ai_pipeline.py
"""Integration tests for the budget ledger, Claude gateway, question generator,
job queue and worker, with Claude replaced by a scripted fake.

Covers:
- budget: reservations count until settled; daily and monthly caps refuse;
  concurrent reservations near the cap -> only one succeeds
- gateway: success settles actual cost; invalid output retried then rejected
  (one usage row per attempt); semantic check retried; refusal; no API key;
  budget exhausted -> no call made; repeated call errors open the circuit
- generator: stores an active question with 4 hints; verifier disagreement
  and SymPy mismatch -> stored as rejected, not served; strict mode -> pending;
  duplicates skipped; objective not on tier -> error
- queue: dedupe while pending; concurrent claims get different jobs; backoff
  then dead; stale running jobs reclaimed
- worker: main loop heartbeats and stops cleanly on SIGTERM;
  runs a generation job; Claude outage -> retried later; missing key
  -> skipped; periodic top-up queues jobs only for topics covered at school,
  and nothing at all without an API key
"""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.budget import BudgetExceededError, BudgetLedger, BudgetLimits
from app.ai.circuit import CircuitBreaker
from app.ai.client import LlmCallError
from app.ai.factory import build_explainer, build_generator
from app.ai.gateway import AiGateway, AiRequest, AiUnavailableError
from app.ai.pricing import TokenUsage
from app.core.config import Settings
from app.jobs import queue
from app.jobs.handlers import JobContext
from app.models.curriculum import LearningObjective, Tier
from app.models.enrolment import StudentSubject
from app.models.ops import AiUsage, Job, JobStatus, UsageStatus
from app.models.question import Hint, ObjectiveProgress, Question, QuestionStatus, QuestionType
from app.models.user import Role
from app.questions.bank import request_generation
from app.questions.generator import TYPES_BY_LEVEL, ObjectiveNotAvailableError, QuestionGenerator
from app.questions.llm_schemas import GeneratedQuestion, Verification
from app.worker import Scheduler, run_once
from app.worker import main as worker_main
from tests.fixtures.factories import (
    FakeClock,
    create_user,
    import_fixture_curriculum,
    make_settings,
)
from tests.fixtures.fake_llm import FakeLlmClient, Reply, mcq, numeric, verification

pytestmark = pytest.mark.integration


@pytest.fixture
def factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory on the test database."""
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def ai_settings(database_url: str) -> Settings:
    """Settings with a small budget so caps are easy to hit."""
    return make_settings(
        database_url,
        anthropic_api_key="sk-test-not-real",
        ai_daily_budget_gbp=Decimal("0.85"),  # $1.00 at 0.85
        ai_monthly_budget_gbp=Decimal("1.70"),  # $2.00
        ai_circuit_failure_threshold=2,
    )


def _gateway(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: FakeLlmClient | None,
    clock: FakeClock,
) -> AiGateway:
    from app.ai.factory import budget_limits

    return AiGateway(
        client,
        BudgetLedger(factory, budget_limits(settings)),
        CircuitBreaker(clock, settings.ai_circuit_failure_threshold, 60),
        settings,
        clock,
    )


async def _objective(session: AsyncSession, ref: str) -> uuid.UUID:
    objective_id = await session.scalar(
        select(LearningObjective.id).where(LearningObjective.ref == ref)
    )
    assert objective_id is not None
    return objective_id


async def _usage_rows(session: AsyncSession) -> list[AiUsage]:
    return list((await session.scalars(select(AiUsage).order_by(AiUsage.created_at))).all())


# ------------------------------------------------------------------ budget


async def test_reservations_should_count_until_settled_and_caps_refuse(
    factory: async_sessionmaker[AsyncSession], session: AsyncSession, clock: FakeClock
) -> None:
    ledger = BudgetLedger(
        factory, BudgetLimits(daily_usd=Decimal("1.00"), monthly_usd=Decimal("5"))
    )
    first = await ledger.reserve(
        purpose="t", model="m", worst_case_usd=Decimal("0.60"), now=clock.now()
    )

    with pytest.raises(BudgetExceededError, match="daily"):
        await ledger.reserve(
            purpose="t", model="m", worst_case_usd=Decimal("0.60"), now=clock.now()
        )

    await ledger.settle(first, TokenUsage(input_tokens=10), Decimal("0.10"), "req")
    await ledger.reserve(purpose="t", model="m", worst_case_usd=Decimal("0.60"), now=clock.now())
    statuses = sorted(r.status.value for r in await _usage_rows(session))
    assert statuses == ["reserved", "settled"]


async def test_monthly_cap_should_apply_across_days(
    factory: async_sessionmaker[AsyncSession], clock: FakeClock
) -> None:
    ledger = BudgetLedger(
        factory, BudgetLimits(daily_usd=Decimal("1.00"), monthly_usd=Decimal("1.50"))
    )
    await ledger.reserve(purpose="t", model="m", worst_case_usd=Decimal("0.90"), now=clock.now())
    clock.advance(days=1)

    with pytest.raises(BudgetExceededError, match="monthly"):
        await ledger.reserve(
            purpose="t", model="m", worst_case_usd=Decimal("0.90"), now=clock.now()
        )


async def test_concurrent_reservations_near_cap_should_not_both_succeed(
    factory: async_sessionmaker[AsyncSession], clock: FakeClock
) -> None:
    ledger = BudgetLedger(
        factory, BudgetLimits(daily_usd=Decimal("1.00"), monthly_usd=Decimal("5"))
    )

    results = await asyncio.gather(
        *(
            ledger.reserve(purpose="t", model="m", worst_case_usd=Decimal("0.60"), now=clock.now())
            for _ in range(4)
        ),
        return_exceptions=True,
    )

    assert sum(1 for r in results if isinstance(r, uuid.UUID)) == 1
    assert sum(1 for r in results if isinstance(r, BudgetExceededError)) == 3


# ------------------------------------------------------------------ gateway


async def test_gateway_should_return_valid_output_and_settle_cost(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    client = FakeLlmClient().add(Verification, Reply(verification()))
    gateway = _gateway(factory, ai_settings, client, clock)

    result = await gateway.structured(
        AiRequest("verify", "claude-haiku-5-5", "sys", "user", Verification)
    )

    [row] = await _usage_rows(session)
    assert result.answer_is_correct is True
    assert row.status is UsageStatus.SETTLED
    assert row.cost_usd > 0
    assert (row.input_tokens, row.cache_read_tokens, row.request_id) == (1200, 900, "req_test")


async def test_gateway_should_retry_invalid_output_then_give_up(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    client = FakeLlmClient().add(
        Verification, Reply(None), Reply(None, stop_reason="refusal"), Reply(None)
    )
    gateway = _gateway(factory, ai_settings, client, clock)

    with pytest.raises(AiUnavailableError) as exc:
        await gateway.structured(
            AiRequest("verify", "claude-haiku-5-5", "sys", "user", Verification)
        )

    assert exc.value.reason == "invalid_output"
    assert "declined" in str(exc.value)
    assert len(await _usage_rows(session)) == 3  # 1 + max_validation_retries


async def test_gateway_should_retry_when_semantic_check_fails(
    factory: async_sessionmaker[AsyncSession], ai_settings: Settings, clock: FakeClock
) -> None:
    client = FakeLlmClient().add(GeneratedQuestion, Reply(mcq(marks=9)), Reply(mcq()))
    gateway = _gateway(factory, ai_settings, client, clock)

    result = await gateway.structured(
        AiRequest("gen", "claude-haiku-5-5", "s", "u", GeneratedQuestion),
        check=lambda q: "bad marks" if q.marks > 6 else None,
    )

    assert result.marks == 1
    assert len(client.calls) == 2


async def test_gateway_without_key_should_refuse_immediately(
    factory: async_sessionmaker[AsyncSession], ai_settings: Settings, clock: FakeClock
) -> None:
    gateway = _gateway(factory, ai_settings, None, clock)

    with pytest.raises(AiUnavailableError) as exc:
        await gateway.structured(AiRequest("verify", "claude-haiku-5-5", "s", "u", Verification))

    assert exc.value.reason == "no_api_key"


async def test_gateway_should_not_call_claude_when_budget_exhausted(
    factory: async_sessionmaker[AsyncSession], ai_settings: Settings, clock: FakeClock
) -> None:
    ledger = BudgetLedger(
        factory, BudgetLimits(daily_usd=Decimal("1.00"), monthly_usd=Decimal("2.00"))
    )
    await ledger.reserve(
        purpose="earlier", model="m", worst_case_usd=Decimal("0.999"), now=clock.now()
    )
    client = FakeLlmClient().add(Verification, Reply(verification()))
    gateway = _gateway(factory, ai_settings, client, clock)

    with pytest.raises(AiUnavailableError) as exc:
        await gateway.structured(AiRequest("verify", "claude-haiku-5-5", "s", "u", Verification))

    assert exc.value.reason == "budget"
    assert client.calls == []


async def test_gateway_should_open_circuit_after_repeated_failures(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    error = LlmCallError("timeout", "Claude timed out")
    client = FakeLlmClient().add(Verification, Reply(error=error), Reply(error=error))
    gateway = _gateway(factory, ai_settings, client, clock)
    request = AiRequest("verify", "claude-haiku-5-5", "s", "u", Verification)

    reasons = []
    for _ in range(3):
        with pytest.raises(AiUnavailableError) as exc:
            await gateway.structured(request)
        reasons.append(exc.value.reason)

    assert reasons == ["call_failed", "call_failed", "circuit_open"]
    assert len(client.calls) == 2
    assert {r.status for r in await _usage_rows(session)} == {UsageStatus.FAILED}


# ------------------------------------------------------------------ generator


async def _generator(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: FakeLlmClient | None,
    clock: FakeClock,
) -> QuestionGenerator:
    return build_generator(settings, factory, client, CircuitBreaker(clock, 5, 60), clock)


async def test_generator_should_store_active_question_with_hints(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(mcq()))
        .add(Verification, Reply(verification()))
    )
    generator = await _generator(factory, ai_settings, client, clock)

    question = await generator.generate(objective, Tier.FOUNDATION, 1)

    assert question is not None
    stored = await session.get(Question, question.id)
    hints = await session.scalar(
        select(func.count()).select_from(Hint).where(Hint.question_id == question.id)
    )
    assert stored is not None
    assert (stored.status, stored.verified, stored.tier, hints) == (
        QuestionStatus.ACTIVE,
        True,
        Tier.FOUNDATION,
        4,
    )
    assert "Objective T1: order integers and decimals" in client.calls[0]["user"]


async def test_generator_should_store_rejected_question_without_serving_it(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(numeric(check_expression="7/2 + 1")))
        .add(Verification, Reply(verification(solved_answer="4.75")))
    )
    generator = await _generator(factory, ai_settings, client, clock)
    monkeypatch.setitem(TYPES_BY_LEVEL, 1, (QuestionType.NUMERIC,))

    question = await generator.generate(objective, Tier.FOUNDATION, 1)

    rejected = await session.scalar(select(Question))
    assert question is None
    assert rejected is not None
    assert rejected.status is QuestionStatus.REJECTED
    assert "SymPy" in (rejected.verification_notes or "")


async def test_generator_strict_mode_should_hold_for_review(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    database_url: str,
    clock: FakeClock,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    settings = make_settings(database_url, question_strict_mode=True)
    client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(mcq()))
        .add(Verification, Reply(verification()))
    )
    generator = await _generator(factory, settings, client, clock)

    assert await generator.generate(objective, Tier.FOUNDATION, 1) is None
    stored = await session.scalar(select(Question))
    assert stored is not None
    assert stored.status is QuestionStatus.PENDING_REVIEW


async def test_generator_should_skip_duplicates(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(mcq()), Reply(mcq()))
        .add(Verification, Reply(verification()), Reply(verification()))
    )
    generator = await _generator(factory, ai_settings, client, clock)
    monkeypatch.setitem(TYPES_BY_LEVEL, 1, (QuestionType.MULTIPLE_CHOICE,))

    first = await generator.generate(objective, Tier.FOUNDATION, 1)
    second = await generator.generate(objective, Tier.FOUNDATION, 1)

    assert first is not None
    assert second is None
    assert await session.scalar(select(func.count()).select_from(Question)) == 1


async def test_generator_should_refuse_objective_not_on_tier(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    await import_fixture_curriculum(session)
    higher_only = await _objective(session, "T3")
    generator = await _generator(factory, ai_settings, FakeLlmClient(), clock)

    with pytest.raises(ObjectiveNotAvailableError):
        await generator.generate(higher_only, Tier.FOUNDATION, 1)


# ------------------------------------------------------------------ queue


async def test_enqueue_should_dedupe_pending_jobs(session: AsyncSession, clock: FakeClock) -> None:
    added = [
        await queue.enqueue(session, "k", {}, clock.now(), dedupe_key="same") for _ in range(2)
    ]
    await session.commit()

    assert added == [True, False]


async def test_concurrent_claims_should_take_different_jobs(
    factory: async_sessionmaker[AsyncSession], session: AsyncSession, clock: FakeClock
) -> None:
    for i in range(2):
        await queue.enqueue(session, "k", {"i": i}, clock.now())
    await session.commit()

    async def claim_one() -> uuid.UUID | None:
        async with factory() as s:
            job = await queue.claim(s, clock.now())
            return job.id if job else None

    first, second = await asyncio.gather(claim_one(), claim_one())

    assert first is not None
    assert second is not None
    assert first != second


async def test_failed_job_should_back_off_then_die(session: AsyncSession, clock: FakeClock) -> None:
    await queue.enqueue(session, "k", {}, clock.now(), max_attempts=2)
    await session.commit()

    job = await queue.claim(session, clock.now())
    assert job is not None
    assert await queue.fail(session, job.id, "boom", clock.now()) is JobStatus.QUEUED
    assert await queue.claim(session, clock.now()) is None  # backing off
    clock.advance(seconds=31)
    job = await queue.claim(session, clock.now())
    assert job is not None
    assert await queue.fail(session, job.id, "boom", clock.now()) is JobStatus.DEAD


async def test_stale_running_job_should_be_reclaimed(
    session: AsyncSession, clock: FakeClock
) -> None:
    await queue.enqueue(session, "k", {}, clock.now())
    await session.commit()
    assert await queue.claim(session, clock.now()) is not None

    clock.advance(minutes=11)
    reclaimed = await queue.claim(session, clock.now())

    assert reclaimed is not None
    assert reclaimed.attempts == 2


# ------------------------------------------------------------------ worker


async def _ctx(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: FakeLlmClient | None,
    clock: FakeClock,
) -> JobContext:
    breaker = CircuitBreaker(clock, 5, 60)
    return JobContext(
        factory,
        build_generator(settings, factory, client, breaker, clock),
        build_explainer(settings, factory, client, breaker, clock),
        settings,
        clock,
    )


async def _job(session: AsyncSession, kind: str) -> Job:
    job = await session.scalar(select(Job).where(Job.kind == kind))
    assert job is not None
    await session.refresh(job)
    return job


async def test_worker_should_run_generation_job(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    await queue.enqueue(
        session,
        "generate_question",
        {"objective_id": str(objective), "tier": "foundation", "difficulty": 1},
        clock.now(),
    )
    await session.commit()
    client = (
        FakeLlmClient()
        .add(GeneratedQuestion, Reply(mcq()))
        .add(Verification, Reply(verification()))
    )
    scheduler = Scheduler(last_run={"top_up_bank": clock.now(), "purge_rate_limits": clock.now()})

    worked = await run_once(await _ctx(factory, ai_settings, client, clock), scheduler)

    assert worked is True
    assert (await _job(session, "generate_question")).status is JobStatus.DONE
    assert await session.scalar(select(func.count()).select_from(Question)) == 1


@pytest.mark.parametrize(
    ("has_key", "expected"), [(True, JobStatus.QUEUED), (False, JobStatus.DONE)]
)
async def test_worker_should_retry_outages_and_skip_without_key(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
    has_key: bool,
    expected: JobStatus,
) -> None:
    await import_fixture_curriculum(session)
    objective = await _objective(session, "T1")
    await queue.enqueue(
        session,
        "generate_question",
        {"objective_id": str(objective), "tier": "foundation", "difficulty": 1},
        clock.now(),
    )
    await session.commit()
    client = (
        FakeLlmClient().add(GeneratedQuestion, Reply(error=LlmCallError("connection", "down")))
        if has_key
        else None
    )
    scheduler = Scheduler(last_run={"top_up_bank": clock.now(), "purge_rate_limits": clock.now()})

    await run_once(await _ctx(factory, ai_settings, client, clock), scheduler)

    assert (await _job(session, "generate_question")).status is expected


async def test_top_up_should_queue_only_for_objectives_the_student_has_started(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    ai_settings: Settings,
    clock: FakeClock,
) -> None:
    # Arrange: a Foundation student on M1 who has only started A1. Every topic is
    # open, but untouched skills are generated on demand, not in advance.
    ids = await import_fixture_curriculum(session)
    student = await create_user(session, Role.STUDENT)
    session.add(
        StudentSubject(
            student_id=student.id,
            subject_id=ids.subjects["maths"],
            board_id=ids.boards["board-a"],
            board_confirmed=True,
            tier=Tier.FOUNDATION,
            tier_confirmed=True,
            specification_id=ids.specs["M1"],
            position=0,
        )
    )
    session.add(ObjectiveProgress(user_id=student.id, objective_id=await _objective(session, "A1")))
    await session.commit()
    ctx = await _ctx(factory, ai_settings, None, clock)

    await run_once(ctx, Scheduler(last_run={"purge_rate_limits": clock.now()}))  # schedules top-up
    await run_once(
        ctx, Scheduler(last_run={"purge_rate_limits": clock.now(), "top_up_bank": clock.now()})
    )

    jobs = (
        await session.scalars(select(Job.dedupe_key).where(Job.kind == "generate_question"))
    ).all()
    a1 = await _objective(session, "A1")
    assert sorted(key or "" for key in jobs) == [f"gen:{a1}:foundation:1", f"gen:{a1}:foundation:2"]


async def test_worker_main_should_heartbeat_and_stop_on_sigterm(
    ai_settings: Settings, db_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: a fast poll, and the heartbeat written somewhere private.
    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setattr("app.worker.HEARTBEAT_FILE", heartbeat)
    settings = ai_settings.model_copy(update={"worker_poll_seconds": 0.05})
    task = asyncio.create_task(worker_main(settings, FakeClock()))

    # Act: wait for the first heartbeat, then ask it to stop.
    async with asyncio.timeout(10):
        while not heartbeat.exists():  # noqa: ASYNC110 - polling a file the worker writes
            await asyncio.sleep(0.05)
    os.kill(os.getpid(), signal.SIGTERM)

    # Assert: it exits cleanly on its own.
    async with asyncio.timeout(10):
        await task
    assert task.exception() is None


async def test_top_up_should_do_nothing_without_api_key(
    factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    database_url: str,
    clock: FakeClock,
) -> None:
    ctx = await _ctx(factory, make_settings(database_url), None, clock)

    await run_once(ctx, Scheduler(last_run={"purge_rate_limits": clock.now()}))
    await run_once(
        ctx, Scheduler(last_run={"purge_rate_limits": clock.now(), "top_up_bank": clock.now()})
    )

    assert (
        await session.scalar(
            select(func.count()).select_from(Job).where(Job.kind == "generate_question")
        )
        == 0
    )


async def test_urgent_generation_should_jump_ahead_of_routine_jobs(
    session: AsyncSession, clock: FakeClock
) -> None:
    # Arrange: two routine jobs queued, then one of them becomes urgent.
    await import_fixture_curriculum(session)
    a1, t1 = await _objective(session, "A1"), await _objective(session, "T1")
    now = clock.now()
    assert await request_generation(session, a1, Tier.FOUNDATION, 1, now)
    assert await request_generation(session, t1, Tier.FOUNDATION, 1, now)
    await session.commit()

    # Act: asking again urgently moves the existing job; no duplicate is added.
    added = await request_generation(session, t1, Tier.FOUNDATION, 1, now, urgent=True)
    await session.commit()

    # Assert
    assert added is False
    claimed = await queue.claim(session, now)
    assert claimed is not None
    assert claimed.dedupe_key == f"gen:{t1}:foundation:1"
    assert await session.scalar(select(func.count()).select_from(Job)) == 2


async def test_expedite_should_leave_running_and_sooner_jobs_alone(
    session: AsyncSession, clock: FakeClock
) -> None:
    # Arrange: "soon" is claimed and running; "later" is waiting.
    now = clock.now()
    await queue.enqueue(session, "x", {}, now, dedupe_key="soon", run_after=now - timedelta(days=1))
    await session.commit()
    assert (await queue.claim(session, now)) is not None
    await queue.enqueue(session, "x", {}, now, dedupe_key="later")
    await session.commit()

    # Act
    await queue.expedite(session, "soon", now - timedelta(minutes=5))
    await queue.expedite(session, "later", now - timedelta(minutes=5))
    await session.commit()

    # Assert
    rows = {j.dedupe_key: j for j in (await session.scalars(select(Job))).all()}
    assert rows["soon"].run_after == now - timedelta(days=1)  # running: untouched
    assert rows["later"].run_after == now - timedelta(minutes=5)
