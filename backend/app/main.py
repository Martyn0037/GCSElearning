# backend/app/main.py
"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.admin.tools_router import router as admin_tools_router
from app.ai.factory import build_breaker, build_llm_client
from app.auth.cookies import CSRF_HEADER
from app.auth.router import router as auth_router
from app.core.clock import SystemClock
from app.core.config import Environment, Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.db.session import create_engine, create_session_factory
from app.enrolment.router import router as enrolment_router
from app.gamification.router import admin_router as boundaries_router
from app.gamification.router import challenge_router
from app.gamification.router import me_router as gamification_me_router
from app.guardian.router import router as guardian_router
from app.health.router import router as health_router
from app.learning.router import router as learning_router
from app.practice.me_router import router as me_router
from app.practice.router import router as practice_router
from app.users.router import router as users_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Settings to use; read from the environment when omitted.

    Returns:
        The configured FastAPI app.
    """
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.environment.value, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        # Claude client (None without an API key: bank-only mode) and this
        # process's circuit breaker.
        app.state.llm_client = build_llm_client(settings)
        app.state.circuit = build_breaker(settings, SystemClock())
        try:
            yield
        finally:
            await engine.dispose()

    is_prod = settings.environment is Environment.PRODUCTION
    app = FastAPI(
        title="GCSE Coach API",
        version="1.0.0",
        lifespan=lifespan,
        # No interactive docs in production; the OpenAPI JSON is exported at build time.
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
    )
    register_error_handlers(app)

    # Middleware runs bottom-up: context (trace IDs) is outermost so every
    # response, including CORS rejections and errors, carries a trace ID.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, "Idempotency-Key", "X-Trace-Id"],
        expose_headers=["X-Trace-Id", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Each router carries its full /api/v1/... prefix so route templates (used
    # as metric labels) are complete paths.
    for router in (
        auth_router,
        users_router,
        enrolment_router,
        practice_router,
        challenge_router,
        learning_router,
        me_router,
        gamification_me_router,
        admin_router,
        admin_tools_router,
        boundaries_router,
        guardian_router,
    ):
        app.include_router(router)
    app.include_router(health_router)
    return app
