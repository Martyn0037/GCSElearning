# backend/app/auth/passwords.py
"""Argon2id password hashing."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128

# argon2-cffi defaults follow RFC 9106's second recommended profile
# (Argon2id, 64 MiB, t=3, p=4), which suits a small server.
_hasher = PasswordHasher()

# Verified against when the username doesn't exist, so a login for an unknown
# account takes as long as one for a real account (no user enumeration by timing).
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    """Hash a password with Argon2id.

    Args:
        password: The plaintext password.

    Returns:
        An encoded Argon2id hash including its parameters and salt.
    """
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Check a password against a stored hash in roughly constant time.

    Args:
        password_hash: The stored hash, or ``None`` if the user doesn't exist.
        password: The plaintext password to check.

    Returns:
        ``True`` only if the user exists and the password matches.
    """
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Return whether a hash was made with weaker-than-current parameters."""
    return _hasher.check_needs_rehash(password_hash)
