# backend/app/auth/service.py
"""Authentication use cases: login, refresh rotation, logout, admin password reset."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import audit
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.tokens import (
    hash_refresh_token,
    issue_access_token,
    new_opaque_token,
)
from app.core.config import Settings
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.metrics import LOGIN_ATTEMPTS
from app.models.refresh_token import RefreshToken
from app.models.user import Role, User

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_MESSAGE = (
    "That username/email and password didn't match, or the account is temporarily locked."
)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Tokens handed to the client after login or refresh."""

    user: User
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def normalise_identifier(identifier: str) -> str:
    """Lower-case and trim a username or email for lookup and storage."""
    return identifier.strip().lower()


class AuthService:
    """Authentication operations for one request.

    Each public method is a unit of work: it commits its own changes before
    returning or raising, so security state (failed-login counts, revocations,
    audit events) is persisted even when the request fails.
    """

    def __init__(self, session: AsyncSession, settings: Settings, now: datetime) -> None:
        """Create the service.

        Args:
            session: Database session for this request.
            settings: Application settings.
            now: The request's current time (UTC), fixed for consistency.
        """
        self._session = session
        self._settings = settings
        self._now = now

    async def login(self, identifier: str, password: str, ip_hash: str | None) -> IssuedSession:
        """Verify credentials and start a new session (refresh-token family).

        Args:
            identifier: Username (students) or email (guardians, admins).
            password: Plaintext password.
            ip_hash: Hashed client IP for the audit log.

        Returns:
            The newly issued session.

        Raises:
            AuthenticationError: On any failure. The message is the same for
                unknown users, wrong passwords, locked and inactive accounts, so
                the response doesn't reveal which accounts exist.
        """
        key = normalise_identifier(identifier)
        column = User.email if "@" in key else User.username
        user = (
            await self._session.execute(select(User).where(column == key).with_for_update())
        ).scalar_one_or_none()

        # Always run the (slow) hash check, off the event loop, so timing is
        # the same whether or not the account exists.
        password_ok = await asyncio.to_thread(
            verify_password, user.password_hash if user else None, password
        )

        if user is None:
            await self._fail(None, ip_hash, "unknown_user")
        assert user is not None  # noqa: S101 - narrowed by _fail raising
        if not user.is_active:
            await self._fail(user, ip_hash, "inactive", count_failure=False)
        if user.locked_until is not None and user.locked_until > self._now:
            await self._fail(user, ip_hash, "locked", count_failure=False)
        if not password_ok:
            await self._fail(user, ip_hash, "bad_password")

        user.failed_login_count = 0
        user.locked_until = None
        if needs_rehash(user.password_hash):
            user.password_hash = await asyncio.to_thread(hash_password, password)
        issued, _ = self._issue(user, family_id=uuid.uuid4())
        audit.record(
            self._session,
            action="auth.login.succeeded",
            now=self._now,
            actor_user_id=user.id,
            ip_hash=ip_hash,
        )
        await self._session.commit()
        LOGIN_ATTEMPTS.labels("success").inc()
        return issued

    async def _fail(
        self, user: User | None, ip_hash: str | None, reason: str, *, count_failure: bool = True
    ) -> None:
        """Record a failed login, lock the account if needed, commit, and raise."""
        details: dict[str, str | int] = {"reason": reason}
        if user is not None and count_failure:
            user.failed_login_count += 1
            if user.failed_login_count >= self._settings.login_max_failures:
                user.locked_until = self._now + timedelta(
                    seconds=self._settings.login_lockout_seconds
                )
                user.failed_login_count = 0
                details["locked"] = 1
                logger.warning("account_locked", extra={"user_id": str(user.id)})
        audit.record(
            self._session,
            action="auth.login.failed",
            now=self._now,
            target_user_id=user.id if user else None,
            ip_hash=ip_hash,
            details=details,
        )
        await self._session.commit()
        LOGIN_ATTEMPTS.labels(reason).inc()
        raise AuthenticationError(INVALID_CREDENTIALS_MESSAGE, code="INVALID_CREDENTIALS")

    async def refresh(self, raw_token: str | None, ip_hash: str | None) -> IssuedSession:
        """Rotate a refresh token and issue a new access token.

        Presenting an already-rotated token outside the grace window is
        treated as theft: every token in that family is revoked, which logs
        out both the attacker and the real user.

        Args:
            raw_token: The refresh token from the cookie.
            ip_hash: Hashed client IP for the audit log.

        Returns:
            The new session.

        Raises:
            AuthenticationError: If the token is missing, unknown, expired,
                reused, or its user is inactive.
        """
        if not raw_token:
            raise AuthenticationError("Please sign in", code="REFRESH_MISSING")
        token = (
            await self._session.execute(
                select(RefreshToken)
                .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if token is None:
            raise AuthenticationError("Please sign in", code="REFRESH_INVALID")

        if token.revoked_at is not None:
            within_grace = token.replaced_by_id is not None and (
                self._now - token.revoked_at
                <= timedelta(seconds=self._settings.refresh_reuse_grace_seconds)
            )
            if within_grace:
                # Two tabs refreshed at once; the other tab already has the new
                # cookie. Not theft, so don't revoke the family.
                raise AuthenticationError("Session already refreshed", code="REFRESH_RACE")
            await self._revoke_family(token.family_id)
            audit.record(
                self._session,
                action="auth.refresh.reuse_detected",
                now=self._now,
                target_user_id=token.user_id,
                ip_hash=ip_hash,
            )
            await self._session.commit()
            logger.warning("refresh_token_reuse", extra={"user_id": str(token.user_id)})
            raise AuthenticationError("Please sign in again", code="REFRESH_REUSED")

        if token.expires_at <= self._now:
            raise AuthenticationError("Please sign in again", code="REFRESH_EXPIRED")

        user = await self._session.get(User, token.user_id)
        if user is None or not user.is_active:
            await self._revoke_family(token.family_id)
            await self._session.commit()
            raise AuthenticationError("Please sign in again", code="REFRESH_INVALID")

        issued, new_token_id = self._issue(user, family_id=token.family_id)
        token.revoked_at = self._now
        token.replaced_by_id = new_token_id
        await self._session.commit()
        return issued

    async def logout(self, raw_token: str | None, actor_user_id: uuid.UUID | None) -> None:
        """End the session by revoking the refresh token's whole family.

        Safe to call repeatedly or with no/unknown token (idempotent).
        """
        if raw_token:
            family_id = (
                await self._session.execute(
                    select(RefreshToken.family_id).where(
                        RefreshToken.token_hash == hash_refresh_token(raw_token)
                    )
                )
            ).scalar_one_or_none()
            if family_id is not None:
                await self._revoke_family(family_id)
                audit.record(
                    self._session, action="auth.logout", now=self._now, actor_user_id=actor_user_id
                )
        await self._session.commit()

    async def list_students(self, limit: int) -> list[User]:
        """Active student accounts, by name (bounded by ``limit``)."""
        return list(
            (
                await self._session.scalars(
                    select(User)
                    .where(User.role == Role.STUDENT, User.is_active.is_(True))
                    .order_by(User.display_name, User.id)
                    .limit(limit)
                )
            ).all()
        )

    async def admin_reset_password(
        self, admin: User, target_user_id: uuid.UUID, new_password: str
    ) -> None:
        """Set a student's password and sign them out everywhere.

        Args:
            admin: The acting admin.
            target_user_id: The student whose password is reset.
            new_password: The new plaintext password (already length-validated).

        Raises:
            PermissionDeniedError: If ``admin`` isn't an admin.
            NotFoundError: If the target doesn't exist or isn't a student.
        """
        if admin.role is not Role.ADMIN:
            raise PermissionDeniedError()
        target = await self._session.get(User, target_user_id, with_for_update=True)
        if target is None or target.role is not Role.STUDENT:
            raise NotFoundError("Student not found")
        target.password_hash = await asyncio.to_thread(hash_password, new_password)
        target.failed_login_count = 0
        target.locked_until = None
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=self._now)
        )
        audit.record(
            self._session,
            action="admin.password_reset",
            now=self._now,
            actor_user_id=admin.id,
            target_user_id=target.id,
        )
        await self._session.commit()

    def _issue(self, user: User, family_id: uuid.UUID) -> tuple[IssuedSession, uuid.UUID]:
        """Create a refresh-token row and access token; return them with the row ID."""
        raw_refresh = new_opaque_token()
        refresh_expires = self._now + timedelta(seconds=self._settings.refresh_token_ttl_seconds)
        row = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw_refresh),
            issued_at=self._now,
            expires_at=refresh_expires,
        )
        self._session.add(row)
        issued = IssuedSession(
            user=user,
            access_token=issue_access_token(self._settings, user.id, user.role, self._now),
            access_expires_at=self._now
            + timedelta(seconds=self._settings.access_token_ttl_seconds),
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_expires,
        )
        return issued, row.id

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=self._now)
        )
