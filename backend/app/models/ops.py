# backend/app/models/ops.py
"""Operational tables: Claude usage/cost records and the background job queue."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageStatus(StrEnum):
    """A Claude call's budget state."""

    RESERVED = "reserved"  # in flight; worst-case cost held against the budget
    SETTLED = "settled"  # finished; actual cost recorded
    FAILED = "failed"  # errored; cost is whatever was billed (often zero)


class AiUsage(Base):
    """One Claude API call: what it was for, tokens used and what it cost.

    Never stores prompt or response text (the student's answers stay out of it).
    """

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_created_status", "created_at", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[UsageStatus] = mapped_column(
        Enum(UsageStatus, name="usage_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cache_read_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    request_id: Mapped[str | None] = mapped_column(String(80))
    error_type: Mapped[str | None] = mapped_column(String(80))


class JobStatus(StrEnum):
    """Background job lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"  # failed max_attempts times; kept for inspection


class Job(Base):
    """A unit of background work, claimed with ``FOR UPDATE SKIP LOCKED`` (ADR-003)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "run_after"),
        # At most one queued-or-running job per dedupe key.
        Index(
            "uq_jobs_dedupe_active",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("5")
    )
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
