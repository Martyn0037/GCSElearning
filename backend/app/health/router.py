# backend/app/health/router.py
"""Liveness, readiness and Prometheus metrics endpoints.

These sit outside ``/api`` and are not proxied by Caddy, so they are only
reachable from inside the Docker network.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.metrics import DB_POOL_CHECKED_OUT

logger = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

READINESS_TIMEOUT_SECONDS = 2.0


@router.get("/health/live")
async def live() -> dict[str, str]:
    """The process is up and serving requests."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """The service can do useful work: the database answers within 2 seconds."""
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("readiness_failed", extra={"error_type": type(exc).__name__})
        return JSONResponse({"status": "unavailable", "checks": {"database": "fail"}}, 503)
    return JSONResponse({"status": "ok", "checks": {"database": "ok"}})


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus scrape endpoint."""
    engine: AsyncEngine = request.app.state.engine
    checked_out = getattr(engine.pool, "checkedout", None)
    if callable(checked_out):
        DB_POOL_CHECKED_OUT.set(checked_out())
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
