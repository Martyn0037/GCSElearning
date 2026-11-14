# backend/app/core/metrics.py
"""Prometheus metrics (the four golden signals for HTTP)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "HTTP requests by method, route and status",
    ["method", "route", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by method and route",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
DB_POOL_CHECKED_OUT = Gauge(
    "db_pool_connections_in_use", "Database connections currently checked out (saturation)"
)
LOGIN_ATTEMPTS = Counter("auth_login_attempts_total", "Login attempts by outcome", ["outcome"])
