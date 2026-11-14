# backend/app/core/pagination.py
"""Opaque keyset cursors for list endpoints.

A cursor encodes the sort key of the last item returned, ``(created_at, id)``,
so the next page starts strictly after it. Unlike offsets, results stay stable
while rows are added.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import InvalidRequestError

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class Cursor:
    """Position after which the next page starts."""

    created_at: datetime
    id: uuid.UUID

    def encode(self) -> str:
        """Return the opaque, URL-safe string form."""
        raw = json.dumps({"t": self.created_at.isoformat(), "i": str(self.id)}).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str) -> Cursor:
        """Parse a cursor from a request.

        Raises:
            InvalidRequestError: If the cursor is malformed or tampered with.
        """
        try:
            padded = value + "=" * (-len(value) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode()))
            return cls(created_at=datetime.fromisoformat(data["t"]), id=uuid.UUID(data["i"]))
        except (binascii.Error, ValueError, KeyError, TypeError) as exc:
            raise InvalidRequestError("Invalid cursor", code="INVALID_CURSOR") from exc
