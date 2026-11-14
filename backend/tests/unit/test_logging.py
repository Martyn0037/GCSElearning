# backend/tests/unit/test_logging.py
"""Unit tests for JSON logging and redaction.

Covers:
- sensitive keys are masked at any depth (incl. lists); safe keys untouched
- formatter emits the standard fields incl. trace/span IDs from context
- extras are redacted in output; exceptions are included
- configure_logging installs the JSON handler and silences access logs
"""

from __future__ import annotations

import json
import logging

from app.core.context import span_id_var, trace_id_var
from app.core.logging import REDACTED, JsonFormatter, configure_logging, redact


def test_should_redact_sensitive_keys_recursively() -> None:
    data = {
        "user_id": "u1",
        "password": "hunter2",
        "nested": {"refresh_token": "t", "items": [{"answer": "x", "ok": 1}]},
    }

    result = redact(data)

    assert result == {
        "user_id": "u1",
        "password": REDACTED,
        "nested": {"refresh_token": REDACTED, "items": [{"answer": REDACTED, "ok": 1}]},
    }


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_should_emit_standard_fields_with_trace_context() -> None:
    formatter = JsonFormatter("svc", "test")
    t1, t2 = trace_id_var.set("trace-123"), span_id_var.set("span-456")
    try:
        line = json.loads(formatter.format(_record(route="/x", email="a@b.c")))
    finally:
        trace_id_var.reset(t1)
        span_id_var.reset(t2)

    assert line["service"] == "svc"
    assert line["environment"] == "test"
    assert line["level"] == "INFO"
    assert line["trace_id"] == "trace-123"
    assert line["span_id"] == "span-456"
    assert line["route"] == "/x"
    assert line["email"] == REDACTED
    assert line["timestamp"].endswith("+00:00")


def test_formatter_should_include_exception_text() -> None:
    formatter = JsonFormatter("svc", "test")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())

    line = json.loads(formatter.format(record))

    assert "ValueError: boom" in line["exception"]


def test_configure_logging_should_install_json_handler() -> None:
    configure_logging("svc", "test", "warning")

    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert root.level == logging.WARNING
    assert logging.getLogger("uvicorn.access").disabled is True
