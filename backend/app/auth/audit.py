# backend/app/auth/audit.py
"""Writing audit-log events."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_trace_id
from app.models.audit_log import AuditLog


def hash_ip(ip: str | None, salt: str) -> str | None:
    """Return a keyed hash of an IP so it can be correlated but not read back.

    Args:
        ip: The client IP, if known.
        salt: Secret key for the HMAC.

    Returns:
        A hex digest, or ``None`` when the IP is unknown.
    """
    if not ip:
        return None
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


def record(
    session: AsyncSession,
    *,
    action: str,
    now: datetime,
    actor_user_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    ip_hash: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session; it's written when the session commits.

    Args:
        session: Database session.
        action: Event name, e.g. ``auth.login.failed``.
        now: When it happened.
        actor_user_id: Who did it, if known.
        target_user_id: Who it was done to, if different.
        ip_hash: Hashed client IP from :func:`hash_ip`.
        details: Extra non-sensitive context. Never put secrets or free text here.
    """
    session.add(
        AuditLog(
            occurred_at=now,
            action=action,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            ip_hash=ip_hash,
            trace_id=current_trace_id(),
            details=details or {},
        )
    )
