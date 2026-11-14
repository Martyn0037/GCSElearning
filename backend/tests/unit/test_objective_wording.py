# backend/tests/unit/test_objective_wording.py
"""Unit tests for picking an objective's wording for a student's tier.

Covers: shared statement, Higher extension, Higher-only statement, untiered subject.
"""

from __future__ import annotations

import pytest

from app.models.curriculum import LearningObjective, Tier


@pytest.mark.parametrize(
    ("foundation", "higher", "tier", "expected"),
    [
        ("order integers", None, Tier.FOUNDATION, "order integers"),
        ("order integers", None, Tier.HIGHER, "order integers"),
        ("roots", "roots and fractional indices", Tier.FOUNDATION, "roots"),
        ("roots", "roots and fractional indices", Tier.HIGHER, "roots and fractional indices"),
        (None, "surds", Tier.FOUNDATION, None),
        (None, "surds", Tier.HIGHER, "surds"),
        ("read a play", None, None, "read a play"),
    ],
    ids=[
        "shared_foundation",
        "shared_higher",
        "extended_foundation",
        "extended_higher",
        "higher_only_on_foundation",
        "higher_only_on_higher",
        "untiered",
    ],
)
def test_text_for_should_return_wording_for_tier(
    foundation: str | None, higher: str | None, tier: Tier | None, expected: str | None
) -> None:
    objective = LearningObjective(foundation_text=foundation, higher_text=higher)

    assert objective.text_for(tier) == expected
