# backend/app/core/config.py
"""Application settings loaded from environment variables.

All environment-specific values (secrets, URLs, origins) come from the
environment. Nothing here has a production-usable default for a secret.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SECRET_LENGTH = 32


class Environment(StrEnum):
    """Deployment environment name."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Typed application settings.

    Attributes:
        environment: Which environment the service runs in.
        service_name: Name stamped on every log line.
        database_url: SQLAlchemy async URL, e.g. ``postgresql+asyncpg://...``.
        db_pool_size: Connections kept open per process.
        db_max_overflow: Extra connections allowed under burst load.
        db_statement_timeout_ms: Server-side statement timeout per connection.
        jwt_secret: HMAC key for access tokens. At least 32 characters.
        jwt_issuer: ``iss`` claim written and required on access tokens.
        jwt_audience: ``aud`` claim written and required on access tokens.
        access_token_ttl_seconds: Lifetime of an access token.
        refresh_token_ttl_seconds: Lifetime of a refresh token.
        refresh_reuse_grace_seconds: Window in which a just-rotated refresh token
            is treated as a benign race (two tabs) instead of theft.
        cookie_secure: Whether auth cookies carry the ``Secure`` attribute.
        cors_origins: Exact origins allowed to call the API. Never ``*``.
        login_max_failures: Failed logins before an account is locked.
        login_lockout_seconds: How long an account stays locked.
        login_ip_limit_per_minute: Login attempts allowed per IP per minute.
        audit_ip_salt: Secret used to hash IP addresses in the audit log so raw
            IPs (personal data) are never stored.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    environment: Environment = Environment.DEVELOPMENT
    service_name: str = "gcse-coach-api"
    log_level: str = "INFO"

    database_url: str
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_statement_timeout_ms: int = Field(default=5000, ge=100)

    jwt_secret: SecretStr
    jwt_issuer: str = "gcse-coach"
    jwt_audience: str = "gcse-coach-web"
    access_token_ttl_seconds: int = Field(default=15 * 60, ge=60, le=60 * 60)
    refresh_token_ttl_seconds: int = Field(default=14 * 24 * 3600, ge=3600)
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0, le=60)

    cookie_secure: bool = True
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    login_max_failures: int = Field(default=5, ge=1)
    login_lockout_seconds: int = Field(default=15 * 60, ge=60)
    login_ip_limit_per_minute: int = Field(default=10, ge=1)

    audit_ip_salt: SecretStr

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a list."""
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        """Refuse the wildcard origin; CORS must be an explicit allowlist."""
        if any(origin == "*" for origin in value):
            raise ValueError("CORS wildcard '*' is not allowed; list exact origins")
        return value

    @field_validator("jwt_secret", "audit_ip_salt")
    @classmethod
    def _require_strong_secret(cls, value: SecretStr) -> SecretStr:
        """Reject short secrets so a placeholder can't reach production."""
        if len(value.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"secret must be at least {MIN_SECRET_LENGTH} characters")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, read once from the environment.

    Returns:
        The validated settings.

    Raises:
        pydantic.ValidationError: If a required value is missing or invalid.
    """
    return Settings()
