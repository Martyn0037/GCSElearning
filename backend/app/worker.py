# backend/app/worker.py
"""Background worker: runs queued jobs and schedules periodic ones.

Run with ``python -m app.worker``. Stops cleanly on SIGTERM/SIGINT after the
current job. Touches ``/tmp/worker-heartbeat`` every loop for the container
health check. Several workers can run at once (jobs are claimed with
``SKIP LOCKED``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.ai.factory import build_breaker, build_generator, build_llm_client
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.context import trace_id_var
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.jobs import queue
from app.jobs.handlers import (
    HANDLERS,
    PURGE_RATE_LIMITS_JOB,
    TOP_UP_JOB,
    JobContext,
    RetryLaterError,
)

logger = logging.getLogger("app.worker")

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")  # noqa: S108 - tmpfs in the container
PERIODIC: dict[str, timedelta] = {
    TOP_UP_JOB: timedelta(minutes=10),
    PURGE_RATE_LIMITS_JOB: timedelta(hours=1),
}


@dataclass
class Scheduler:
    """Enqueues periodic jobs when they're due (dedupe keys prevent pile-ups)."""

    last_run: dict[str, datetime] = field(default_factory=dict)

    def due(self, now: datetime) -> list[str]:
        """Job kinds whose interval has elapsed; marks them as scheduled."""
        kinds = [
            k
            for k, every in PERIODIC.items()
            if k not in self.last_run or now - self.last_run[k] >= every
        ]
        for kind in kinds:
            self.last_run[kind] = now
        return kinds


async def run_once(ctx: JobContext, scheduler: Scheduler) -> bool:
    """Schedule due periodic jobs, then run at most one queued job.

    Returns:
        Whether a job was run (so the caller can skip sleeping).
    """
    now = ctx.clock.now()
    async with ctx.session_factory() as session:
        for kind in scheduler.due(now):
            await queue.enqueue(session, kind, {}, now, dedupe_key=kind, max_attempts=1)
        await session.commit()
        job = await queue.claim(session, now)
    if job is None:
        return False

    token = trace_id_var.set(f"job-{job.id.hex}")
    try:
        handler = HANDLERS.get(job.kind)
        if handler is None:
            raise RetryLaterError(f"unknown job kind {job.kind!r}")
        await handler(ctx, job.payload)
    except Exception as exc:
        async with ctx.session_factory() as session:
            status = await queue.fail(
                session, job.id, f"{type(exc).__name__}: {exc}", ctx.clock.now()
            )
        level = logging.INFO if isinstance(exc, RetryLaterError) else logging.ERROR
        logger.log(
            level,
            "job_failed",
            extra={"kind": job.kind, "status": status.value},
            exc_info=level == logging.ERROR,
        )
    else:
        async with ctx.session_factory() as session:
            await queue.complete(session, job.id, ctx.clock.now())
        logger.info("job_done", extra={"kind": job.kind})
    finally:
        trace_id_var.reset(token)
    return True


async def main(settings: Settings | None = None, clock: Clock | None = None) -> None:
    """Run until signalled."""
    settings = settings or get_settings()
    clock = clock or SystemClock()
    configure_logging(
        f"{settings.service_name}-worker", settings.environment.value, settings.log_level
    )
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    generator = build_generator(
        settings, session_factory, build_llm_client(settings), build_breaker(settings, clock), clock
    )
    ctx = JobContext(session_factory, generator, settings, clock)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("worker_started", extra={"claude": settings.anthropic_api_key is not None})
    scheduler = Scheduler()
    try:
        while not stop.is_set():
            # Tiny tmpfs write; not worth a thread hop.
            HEARTBEAT_FILE.touch()  # noqa: ASYNC240
            try:
                worked = await run_once(ctx, scheduler)
            except Exception:
                logger.exception("worker_loop_error")
                worked = False
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        await engine.dispose()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
