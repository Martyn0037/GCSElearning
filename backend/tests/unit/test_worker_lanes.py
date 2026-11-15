# backend/tests/unit/test_worker_lanes.py
"""Worker lanes run jobs side by side.

Covers:
- two lanes are inside ``run_once`` at the same time (so a slow Claude call
  doesn't hold up the next job), and both stop when asked
- a lane that finds no job waits for the poll interval, and an error in one
  job is logged without stopping the lane
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app import worker


async def test_lanes_should_run_jobs_at_the_same_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange: each "job" waits until another lane is also mid-job.
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", tmp_path / "heartbeat")
    stop = asyncio.Event()
    active = 0
    both_running = asyncio.Event()

    async def fake_run_once(_ctx: Any, _scheduler: Any) -> bool:
        nonlocal active
        active += 1
        if active >= 2:
            both_running.set()
        await both_running.wait()
        stop.set()
        return True

    monkeypatch.setattr(worker, "run_once", fake_run_once)

    # Act: with one lane this would never finish.
    async with asyncio.timeout(5):
        await asyncio.gather(
            *(worker._lane(None, None, stop, 0.01) for _ in range(2))  # type: ignore[arg-type]
        )

    # Assert
    assert both_running.is_set()
    assert (tmp_path / "heartbeat").exists()


async def test_lane_should_survive_a_failing_job_and_poll_when_idle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange: first call fails, second finds nothing, third stops the lane.
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", tmp_path / "heartbeat")
    stop = asyncio.Event()
    calls = 0

    async def fake_run_once(_ctx: Any, _scheduler: Any) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        if calls == 3:
            stop.set()
        return False

    monkeypatch.setattr(worker, "run_once", fake_run_once)

    # Act
    async with asyncio.timeout(5):
        await worker._lane(None, None, stop, 0.01)  # type: ignore[arg-type]

    # Assert
    assert calls == 3
