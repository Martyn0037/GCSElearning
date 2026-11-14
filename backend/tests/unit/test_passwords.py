# backend/tests/unit/test_passwords.py
"""Unit tests for Argon2id password hashing.

Covers:
- hash uses Argon2id and verifies the right password
- wrong password, missing user (None hash) and corrupt hash all return False
- the dummy hash's password can't sign in a non-existent user
- outdated parameters are detected for rehash
"""

from __future__ import annotations

from argon2 import PasswordHasher

from app.auth.passwords import hash_password, needs_rehash, verify_password


def test_should_hash_with_argon2id_and_verify_correct_password() -> None:
    hashed = hash_password("a-good-password")

    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a-good-password") is True


def test_should_reject_wrong_password() -> None:
    assert verify_password(hash_password("a-good-password"), "a-bad-password") is False


def test_should_reject_when_user_does_not_exist() -> None:
    assert verify_password(None, "anything") is False


def test_should_not_sign_in_missing_user_with_dummy_password() -> None:
    assert verify_password(None, "timing-equaliser-not-a-real-password") is False


def test_should_reject_corrupt_hash_without_raising() -> None:
    assert verify_password("not-a-hash", "anything") is False


def test_should_flag_hash_with_weaker_parameters_for_rehash() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8192).hash("pw")

    assert needs_rehash(weak) is True
    assert needs_rehash(hash_password("pw")) is False
