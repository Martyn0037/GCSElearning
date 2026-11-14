# backend/app/models/rate_limit.py
"""Fixed-window request counters (see ADR-004)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitCounter(Base):
    """How many requests ``key`` has made in the window starting ``window_start``."""

    __tablename__ = "rate_limit_counters"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False)
