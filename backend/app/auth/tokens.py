# backend/app/auth/tokens.py
"""Access-token (JWT) and refresh/CSRF token primitives."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.models.user import Role

JWT_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "role", "jti"]


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """The verified contents of an access token."""

    user_id: uuid.UUID
    role: Role
    expires_at: datetime


def issue_access_token(settings: Settings, user_id: uuid.UUID, role: Role, now: datetime) -> str:
    """Create a signed, short-lived access token.

    Args:
        settings: Supplies the key, issuer, audience and lifetime.
        user_id: The subject.
        role: The user's role at issue time.
        now: Issue time (UTC).

    Returns:
        The encoded JWT.
    """
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(settings: Settings, token: str, now: datetime) -> AccessClaims:
    """Verify an access token's signature, expiry, issuer and audience.

    Args:
        settings: Supplies the key, issuer and audience.
        token: The encoded JWT.
        now: Current time, used for the expiry check.

    Returns:
        The verified claims.

    Raises:
        AuthenticationError: If the token is invalid, expired or malformed.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            # Time checks use the injected clock below, not the system clock.
            options={"require": _REQUIRED_CLAIMS, "verify_exp": False, "verify_iat": False},
        )
        expires_at = datetime.fromtimestamp(payload["exp"], tz=now.tzinfo)
        if expires_at <= now:
            raise AuthenticationError("Session expired", code="TOKEN_EXPIRED")
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]), role=Role(payload["role"]), expires_at=expires_at
        )
    except AuthenticationError:
        raise
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError("Invalid session", code="TOKEN_INVALID") from exc


def new_opaque_token() -> str:
    """Return a 256-bit URL-safe random token (refresh or CSRF)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> bytes:
    """Hash a refresh token for storage and lookup.

    A fast hash is correct here: the token is 256 bits of randomness, so it
    can't be brute-forced, and lookups need to be quick.
    """
    return hashlib.sha256(token.encode("utf-8")).digest()


def tokens_match(expected: str | None, provided: str | None) -> bool:
    """Compare two tokens in constant time; ``None`` or empty never matches."""
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
