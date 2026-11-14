# backend/app/core/schemas.py
"""Shared Pydantic base models and the error-response schema for OpenAPI."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

API_V1_PREFIX = "/api/v1"


class ApiModel(BaseModel):
    """Base for request/response bodies: camelCase on the wire, strict input.

    Unknown fields are rejected (allowlist validation).
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=False,
        from_attributes=True,
    )


class ErrorDetail(ApiModel):
    """The body of an error."""

    code: str
    message: str
    trace_id: str | None


class ErrorResponse(ApiModel):
    """The standard error envelope returned by every endpoint."""

    error: ErrorDetail


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 422, 429, 500)
}
