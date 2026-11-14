# backend/tests/unit/test_anthropic_client.py
"""Unit tests for the Anthropic adapter, replaying recorded-style API responses.

The real SDK runs end to end; only the HTTP transport is replaced, so request
shape, response parsing and error mapping are all exercised without network.

Covers:
- a structured reply is parsed into the schema; usage and request ID captured
- the request carries the model, cached system prompt, effort and JSON schema
- refusal stop reason is passed through with no parsed output
- 429 / 500 / timeout / connection failure map to LlmCallError kinds
- a reply that isn't valid JSON for the schema -> no output (retried, not an outage)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.ai.client import AnthropicLlmClient, LlmCallError
from app.questions.llm_schemas import Verification
from tests.fixtures.fake_llm import verification

RECORDED_USAGE = {
    "input_tokens": 512,
    "output_tokens": 230,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 640,
}


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    """A Messages API response body in the recorded shape."""
    return {
        "id": "msg_01Test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": RECORDED_USAGE,
    }


def _client(handler: Callable[[httpx2.Request], httpx2.Response]) -> AnthropicLlmClient:
    transport = httpx2.MockTransport(handler)
    return AnthropicLlmClient(
        api_key="sk-test-not-real",
        timeout_seconds=5,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=transport),
    )


async def _parse(client: AnthropicLlmClient) -> Any:
    return await client.parse(
        model="claude-haiku-5-5",
        system="SYSTEM",
        user="USER",
        schema=Verification,
        max_tokens=500,
        effort="medium",
    )


async def test_should_parse_structured_reply_and_capture_usage() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200, json=_message(verification().model_dump_json()), headers={"request-id": "req_abc"}
        )

    result = await _parse(_client(handler))

    assert result.parsed == verification()
    assert (result.usage.input_tokens, result.usage.cache_read_tokens, result.request_id) == (
        512,
        640,
        "req_abc",
    )
    body = sent[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["messages"] == [{"role": "user", "content": "USER"}]


async def test_should_pass_through_refusal() -> None:
    result = await _parse(
        _client(lambda _: httpx2.Response(200, json=_message("", stop_reason="refusal")))
    )

    assert result.stop_reason == "refusal"
    assert result.parsed is None


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (
            httpx2.Response(
                429,
                json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}},
            ),
            "rate_limited",
        ),
        (
            httpx2.Response(
                500, json={"type": "error", "error": {"type": "api_error", "message": "boom"}}
            ),
            "http_500",
        ),
    ],
    ids=["rate_limited", "server_error"],
)
async def test_should_map_api_failures(response: httpx2.Response, kind: str) -> None:
    with pytest.raises(LlmCallError) as exc:
        await _parse(_client(lambda _: response))

    assert exc.value.kind == kind


async def test_invalid_json_should_return_no_output_rather_than_raise() -> None:
    result = await _parse(_client(lambda _: httpx2.Response(200, json=_message("not json at all"))))

    assert result.parsed is None
    assert result.stop_reason == "end_turn"


@pytest.mark.parametrize(
    ("error", "kind"),
    [(httpx2.ReadTimeout("slow"), "timeout"), (httpx2.ConnectError("down"), "connection")],
)
async def test_should_map_transport_failures(error: Exception, kind: str) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        raise error

    with pytest.raises(LlmCallError) as exc:
        await _parse(_client(handler))

    assert exc.value.kind == kind
