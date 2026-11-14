# backend/tests/unit/test_tokens.py
"""Unit tests for access tokens and opaque-token helpers.

Covers:
- issue/decode round trip; times judged by the injected clock (regression)
- expiry boundary (exactly at exp is expired)
- wrong audience / issuer / key, tampering, alg=none, missing claims -> invalid
- refresh-token hashing is deterministic; random tokens are unique
- constant-time comparison handles None/empty/mismatch
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from app.auth.tokens import (
    decode_access_token,
    hash_refresh_token,
    issue_access_token,
    new_opaque_token,
    tokens_match,
)
from app.core.errors import AuthenticationError
from app.models.user import Role
from tests.fixtures.factories import FIXED_NOW, make_settings

SETTINGS = make_settings()
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def test_should_round_trip_claims() -> None:
    token = issue_access_token(SETTINGS, USER_ID, Role.GUARDIAN, FIXED_NOW)

    claims = decode_access_token(SETTINGS, token, FIXED_NOW + timedelta(minutes=1))

    assert claims.user_id == USER_ID
    assert claims.role is Role.GUARDIAN
    assert claims.expires_at == FIXED_NOW + timedelta(seconds=SETTINGS.access_token_ttl_seconds)


def test_should_treat_token_as_expired_exactly_at_expiry() -> None:
    token = issue_access_token(SETTINGS, USER_ID, Role.STUDENT, FIXED_NOW)
    at_expiry = FIXED_NOW + timedelta(seconds=SETTINGS.access_token_ttl_seconds)

    with pytest.raises(AuthenticationError) as exc:
        decode_access_token(SETTINGS, token, at_expiry)

    assert exc.value.code == "TOKEN_EXPIRED"


@pytest.mark.parametrize(
    "other",
    [
        make_settings(jwt_audience="someone-else"),
        make_settings(jwt_issuer="someone-else"),
        make_settings(jwt_secret="a-different-secret-" + "z" * 32),
    ],
    ids=["audience", "issuer", "key"],
)
def test_should_reject_token_from_mismatched_settings(other: object) -> None:
    token = issue_access_token(SETTINGS, USER_ID, Role.STUDENT, FIXED_NOW)

    with pytest.raises(AuthenticationError) as exc:
        decode_access_token(other, token, FIXED_NOW)  # type: ignore[arg-type]

    assert exc.value.code == "TOKEN_INVALID"


def test_should_reject_unsigned_alg_none_token() -> None:
    forged = jwt.encode(
        {
            "sub": str(USER_ID),
            "role": "admin",
            "iss": SETTINGS.jwt_issuer,
            "aud": SETTINGS.jwt_audience,
            "iat": 0,
            "exp": 9999999999,
            "jti": "x",
        },
        key=None,
        algorithm="none",
    )

    with pytest.raises(AuthenticationError):
        decode_access_token(SETTINGS, forged, FIXED_NOW)


def test_should_reject_token_missing_role_claim() -> None:
    token = jwt.encode(
        {
            "sub": str(USER_ID),
            "iss": SETTINGS.jwt_issuer,
            "aud": SETTINGS.jwt_audience,
            "iat": 0,
            "exp": 9999999999,
            "jti": "x",
        },
        SETTINGS.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError):
        decode_access_token(SETTINGS, token, FIXED_NOW)


def test_should_reject_garbage_token() -> None:
    with pytest.raises(AuthenticationError):
        decode_access_token(SETTINGS, "not.a.jwt", FIXED_NOW)


def test_should_hash_refresh_tokens_deterministically_and_generate_unique_tokens() -> None:
    a, b = new_opaque_token(), new_opaque_token()

    assert a != b
    assert hash_refresh_token(a) == hash_refresh_token(a)
    assert len(hash_refresh_token(a)) == 32


@pytest.mark.parametrize(
    ("expected", "provided", "result"),
    [("abc", "abc", True), ("abc", "abd", False), (None, "abc", False), ("abc", "", False)],
)
def test_tokens_match_should_compare_safely(
    expected: str | None, provided: str | None, result: bool
) -> None:
    assert tokens_match(expected, provided) is result


def test_should_judge_token_times_by_injected_clock_not_system_clock() -> None:
    # Regression: PyJWT's own iat check used the system clock, so a token
    # issued "tomorrow" by the app's clock was rejected as immature.
    tomorrow = FIXED_NOW + timedelta(days=3650)
    token = issue_access_token(SETTINGS, USER_ID, Role.STUDENT, tomorrow)

    claims = decode_access_token(SETTINGS, token, tomorrow + timedelta(minutes=1))

    assert claims.user_id == USER_ID
