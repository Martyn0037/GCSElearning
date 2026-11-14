# backend/app/jobs/queue.py
"""A small Postgres-backed job queue (ADR-003).

- ``enqueue`` is idempotent per ``dedupe_key`` while a job is queued or running.
- ``claim`` takes the oldest due job with ``FOR UPDATE SKIP LOCKED``, so any
  number of workers can run without double-processing.
- Failures back off exponentially; after ``max_attempts`` a job is ``dead``.
- A job left ``running`` by a crashed worker is reclaimed after a timeout.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops import Job, JobStatus

STALE_AFTER = timedelta(minutes=10)
MAX_BACKOFF = timedelta(hours=1)
BASE_BACKOFF_SECONDS = 30


def backoff(attempts: int) -> timedelta:
    """Delay before retry number ``attempts`` (30s, 60s, 120s ... capped at 1h)."""
    return min(timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** max(attempts - 1, 0)), MAX_BACKOFF)


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    now: datetime,
    *,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> bool:
    """Add a job (caller commits).

    Returns:
        ``True`` if added, ``False`` if an identical job is already pending.
    """
    stmt = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            payload=payload,
            dedupe_key=dedupe_key,
            status=JobStatus.QUEUED,
            attempts=0,
            max_attempts=max_attempts,
            run_after=run_after or now,
            created_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[Job.dedupe_key],
            index_where=text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
        )
        .returning(Job.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def claim(session: AsyncSession, now: datetime) -> Job | None:
    """Take the next due job and mark it running (commits).

    Stale running jobs (worker died mid-job) are returned to the queue first.
    """
    await session.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.locked_at < now - STALE_AFTER)
        .values(status=JobStatus.QUEUED, locked_at=None)
    )
    job = await session.scalar(
        select(Job)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= now)
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is not None:
        job.status = JobStatus.RUNNING
        job.locked_at = now
        job.attempts += 1
    await session.commit()
    return job


async def complete(session: AsyncSession, job_id: uuid.UUID, now: datetime) -> None:
    """Mark a job done (commits)."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.DONE, finished_at=now, locked_at=None, last_error=None)
    )
    await session.commit()


async def fail(session: AsyncSession, job_id: uuid.UUID, error: str, now: datetime) -> JobStatus:
    """Record a failure: retry later with backoff, or mark dead (commits).

    Returns:
        The job's new status.
    """
    job = await session.get(Job, job_id, with_for_update=True)
    if job is None:
        await session.commit()
        return JobStatus.DEAD
    job.last_error = error[:2000]
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD
        job.finished_at = now
    else:
        job.status = JobStatus.QUEUED
        job.run_after = now + backoff(job.attempts)
    status = job.status
    await session.commit()
    return status
