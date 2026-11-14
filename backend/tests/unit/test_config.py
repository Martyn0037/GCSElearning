# backend/tests/unit/test_config.py
"""Unit tests for settings validation.

Covers:
- comma-separated CORS origins are parsed into a list
- wildcard CORS origin is rejected
- short JWT secret / IP salt are rejected
- defaults: secure cookies on, 15-minute access tokens
- a blank Anthropic key counts as not configured
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.factories import make_settings


def test_should_parse_comma_separated_cors_origins() -> None:
    settings = make_settings(cors_origins="https://a.test, https://b.test,")

    assert settings.cors_origins == ["https://a.test", "https://b.test"]


def test_should_reject_wildcard_cors_origin() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        make_settings(cors_origins="https://a.test,*")


@pytest.mark.parametrize("field", ["jwt_secret", "audit_ip_salt"])
def test_should_reject_secrets_shorter_than_32_characters(field: str) -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(**{field: "too-short"})


def test_should_default_to_secure_cookies_and_short_access_tokens() -> None:
    settings = make_settings()

    assert settings.cookie_secure is True
    assert settings.access_token_ttl_seconds == 900


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_anthropic_key_should_mean_not_configured(value: str) -> None:
    assert make_settings(anthropic_api_key=value).anthropic_api_key is None
