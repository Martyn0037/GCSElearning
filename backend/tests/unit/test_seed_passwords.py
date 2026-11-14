# backend/tests/unit/test_seed_passwords.py
"""Unit tests for how the seed command obtains passwords.

Covers:
- a valid environment value is used without prompting
- a too-short environment value is rejected with a message naming the variable
- no environment value and no terminal -> clear error
- prompting: accepts a matching pair; re-asks after too-short or mismatched entries
- gives up after the maximum number of attempts
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from app.cli.seed_users import MAX_PROMPT_ATTEMPTS, PasswordError, resolve_password


def _scripted(answers: list[str]) -> Callable[[str], str]:
    replies: Iterator[str] = iter(answers)
    return lambda _prompt: next(replies)


def _never_called(_prompt: str) -> str:
    raise AssertionError("should not prompt")


def test_should_use_environment_value_without_prompting() -> None:
    result = resolve_password(
        "SEED_X", "Admin", env={"SEED_X": "long-enough-pw"}, prompt=_never_called
    )

    assert result == "long-enough-pw"


def test_should_reject_too_short_environment_value() -> None:
    with pytest.raises(PasswordError, match="SEED_X must be at least 10"):
        resolve_password("SEED_X", "Admin", env={"SEED_X": "short"}, prompt=_never_called)


def test_should_explain_when_no_value_and_no_terminal() -> None:
    with pytest.raises(PasswordError, match="Set SEED_X, or run this in a terminal"):
        resolve_password("SEED_X", "Admin", env={}, prompt=None)


def test_should_accept_matching_prompted_password() -> None:
    result = resolve_password(
        "SEED_X", "Admin", env={}, prompt=_scripted(["a-good-password", "a-good-password"])
    )

    assert result == "a-good-password"


def test_should_ask_again_after_too_short_or_mismatched_entries() -> None:
    answers = ["short", "a-good-password", "different-one", "a-good-password", "a-good-password"]

    result = resolve_password("SEED_X", "Admin", env={}, prompt=_scripted(answers))

    assert result == "a-good-password"


def test_should_give_up_after_max_attempts() -> None:
    with pytest.raises(PasswordError, match="No valid admin password"):
        resolve_password(
            "SEED_X", "Admin", env={}, prompt=_scripted(["short"] * MAX_PROMPT_ATTEMPTS)
        )
