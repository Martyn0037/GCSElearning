# backend/app/practice/ladder.py
"""The difficulty ladder for one objective (brief section 5, ADR-005).

- Up a level after 3 correct in a row, or 4 of the last 5 correct (80%).
- Down a level after 2 misses in a row at the same level.
- A hint-assisted answer (full solution seen) is neither a success nor a miss:
  it breaks a run of correct answers but doesn't push the student down.
Levels run 1-5; history resets whenever the level changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MIN_LEVEL = 1
MAX_LEVEL = 5
WINDOW = 5


class Outcome(StrEnum):
    """How an answer went."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    ASSISTED = "assisted"


@dataclass(frozen=True, slots=True)
class LadderState:
    """Current level and recent outcomes at that level (newest last)."""

    level: int
    recent: tuple[Outcome, ...] = ()


def advance(state: LadderState, outcome: Outcome) -> LadderState:
    """Apply one outcome and return the new state.

    Args:
        state: The state before the answer.
        outcome: How the answer went.

    Returns:
        The new state; ``recent`` is cleared when the level changes.
    """
    recent = (*state.recent, outcome)[-WINDOW:]
    correct_run = 0
    for item in reversed(recent):
        if item is not Outcome.CORRECT:
            break
        correct_run += 1
    last_five_correct = sum(1 for o in recent if o is Outcome.CORRECT)

    if outcome is Outcome.CORRECT and (
        correct_run >= 3 or (len(recent) == WINDOW and last_five_correct >= 4)
    ):
        return (
            LadderState(min(state.level + 1, MAX_LEVEL))
            if state.level < MAX_LEVEL
            else LadderState(state.level, recent)
        )
    if outcome is Outcome.INCORRECT and recent[-2:] == (Outcome.INCORRECT, Outcome.INCORRECT):
        return (
            LadderState(max(state.level - 1, MIN_LEVEL))
            if state.level > MIN_LEVEL
            else LadderState(state.level, recent)
        )
    return LadderState(state.level, recent)
