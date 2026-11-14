# backend/app/core/middleware.py
"""ASGI middleware: trace IDs, request logging/metrics, and security headers.

Written as plain ASGI (not ``BaseHTTPMiddleware``) so they add little overhead
and don't break streaming responses or context-variable propagation.
"""

from __future__ import annotations

import logging
import re
import secrets
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import span_id_var, trace_id_var
from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY

logger = logging.getLogger("app.request")

TRACE_HEADER = "x-trace-id"
_INCOMING_TRACE_HEADERS = (b"x-trace-id", b"x-request-id")
# Only accept well-formed incoming IDs, so a client can't inject log content.
_VALID_TRACE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

SECURITY_HEADERS: dict[str, str] = {
    # The API only returns JSON, so nothing may load or frame it.
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
    "cache-control": "no-store",
}


def _incoming_trace_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name in _INCOMING_TRACE_HEADERS:
            candidate = value.decode("latin-1")
            if _VALID_TRACE_ID.match(candidate):
                return str(candidate)
    return None


class RequestContextMiddleware:
    """Assign trace/span IDs, log each request, and record metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap one HTTP request; other scope types pass straight through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = _incoming_trace_id(scope) or secrets.token_hex(16)
        trace_token = trace_id_var.set(trace_id)
        span_token = span_id_var.set(secrets.token_hex(8))
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[TRACE_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            # Use the matched route template, never the raw path, to keep
            # metric cardinality bounded and IDs out of labels.
            route = scope.get("route")
            route_label = getattr(route, "path", "unmatched")
            REQUEST_COUNT.labels(scope["method"], route_label, str(status_code)).inc()
            REQUEST_LATENCY.labels(scope["method"], route_label).observe(elapsed)
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "route": route_label,
                    "status": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            trace_id_var.reset(trace_token)
            span_id_var.reset(span_token)


class SecurityHeadersMiddleware:
    """Add strict security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Add headers to the response start message."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
