# backend/app/core/context.py
"""Per-request context (trace and span IDs) carried in context variables.

Context variables are task-local in asyncio, so concurrent requests never see
each other's IDs.
"""

from __future__ import annotations

from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)


def current_trace_id() -> str | None:
    """Return the trace ID of the request being handled, if any."""
    return trace_id_var.get()


def current_span_id() -> str | None:
    """Return the span ID of the request being handled, if any."""
    return span_id_var.get()
