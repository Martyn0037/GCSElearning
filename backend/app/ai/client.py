# backend/app/ai/client.py
"""The narrow interface the app uses to call Claude, and its Anthropic implementation.

Everything else depends on :class:`LlmClient`, so tests swap in a fake and
no test ever calls the real API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import httpx2
import pydantic
from pydantic import BaseModel

from app.ai.pricing import TokenUsage

Effort = Literal["low", "medium", "high"]


class LlmCallError(Exception):
    """Claude couldn't be reached or returned an error (retryable by nature).

    Attributes:
        kind: Short machine-readable category for usage records and logs.
        usage: Tokens billed before the failure, if known.
    """

    def __init__(self, kind: str, message: str, usage: TokenUsage | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.usage = usage


@dataclass(frozen=True, slots=True)
class LlmResponse[T: BaseModel]:
    """A structured response: the parsed object (``None`` if it didn't validate)."""

    parsed: T | None
    stop_reason: str | None
    usage: TokenUsage
    request_id: str | None


class LlmClient(Protocol):
    """Calls Claude and parses the reply into ``schema``."""

    async def parse[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int,
        effort: Effort,
    ) -> LlmResponse[T]:
        """Send one request with structured output.

        Raises:
            LlmCallError: On connection, timeout, rate limit, or API errors.
        """
        ...


class AnthropicLlmClient:
    """:class:`LlmClient` backed by the official async SDK.

    The SDK retries 408/409/429/5xx and connection errors with backoff
    (``max_retries``); timeouts bound each attempt.
    """

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float,
        max_retries: int = 2,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        """Create the client. The key comes from settings, never from code.

        Args:
            api_key: Anthropic API key.
            timeout_seconds: Per-attempt timeout.
            max_retries: SDK retries for retryable errors.
            http_client: Override the transport (tests replay recorded responses).
        """
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def parse[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int,
        effort: Effort,
    ) -> LlmResponse[T]:
        """See :meth:`LlmClient.parse`.

        Uses ``messages.create`` with the schema as ``output_config.format`` and
        validates the text here, rather than ``messages.parse``: that raises on
        an empty or invalid reply, which would hide refusals and make a bad
        reply look like an outage. Here both come back as ``parsed=None``.
        """
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                # The system prompt is identical across calls of the same kind,
                # so caching it makes repeat calls cheaper.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)},
                },
            )
        except anthropic.APITimeoutError as exc:
            raise LlmCallError("timeout", "Claude timed out") from exc
        except anthropic.RateLimitError as exc:
            raise LlmCallError("rate_limited", "Claude rate limit") from exc
        except anthropic.APIStatusError as exc:
            raise LlmCallError(
                f"http_{exc.status_code}", f"Claude API error {exc.status_code}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LlmCallError("connection", "Could not reach Claude") from exc

        parsed: T | None = None
        if response.stop_reason != "refusal":
            text = "".join(block.text for block in response.content if block.type == "text")
            try:
                parsed = schema.model_validate_json(text)
            except pydantic.ValidationError:
                parsed = None  # the gateway retries
        usage = response.usage
        return LlmResponse(
            parsed=parsed,
            stop_reason=response.stop_reason,
            usage=TokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
            ),
            request_id=response._request_id,
        )
