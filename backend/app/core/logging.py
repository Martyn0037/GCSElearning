# backend/app/core/logging.py
"""Structured JSON logging with trace IDs and redaction of sensitive fields."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import current_span_id, current_trace_id

REDACTED = "[REDACTED]"

# Any extra field whose name matches is masked, at any nesting depth. Student
# free-text answers are covered by "answer"; message bodies by "body"/"content".
_SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|authorization|cookie|csrf|answer|body|content|email",
    re.IGNORECASE,
)

# Attributes every LogRecord has; anything else was passed via ``extra=``.
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive keys masked, recursively.

    Args:
        value: Any JSON-like structure.

    Returns:
        The same structure with values under sensitive keys replaced.
    """
    if isinstance(value, dict):
        return {
            k: REDACTED if _SENSITIVE_KEY.search(str(k)) else redact(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def __init__(self, service: str, environment: str) -> None:
        """Create a formatter.

        Args:
            service: Service name written on every line.
            environment: Environment name written on every line.
        """
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as JSON with the standard fields first."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "environment": self._environment,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id(),
            "span_id": current_span_id(),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        payload.update(redact(extras))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service: str, environment: str, level: str = "INFO") -> None:
    """Route all logging (including uvicorn's) through the JSON formatter.

    Args:
        service: Service name for the ``service`` field.
        environment: Environment name for the ``environment`` field.
        level: Root log level name.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, environment))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Access logs would duplicate our request log and include raw query strings.
    logging.getLogger("uvicorn.access").disabled = True
