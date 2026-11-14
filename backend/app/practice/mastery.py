# backend/app/practice/mastery.py
"""Bayesian Knowledge Tracing: how likely it is a student has mastered an objective (ADR-005).

Fixed, documented parameters (no fitting: one student never produces enough
data to fit them):

- ``P_INIT``: prior before any answer.
- ``P_LEARN``: chance of learning from each practice opportunity.
- ``SLIP`` by difficulty: chance of a careless error despite mastery; harder
  questions have more room to slip.
- ``GUESS`` by question type: chance of a right answer without mastery
  (1 in 4 for multiple choice, low for typed answers).

A hint-assisted answer (full solution seen) is not evidence either way, so
only the learning step applies.

Estimates are kept within ``[P_FLOOR, P_CEIL]``: at exactly 0 or 1 the
formula can never move again (a wrong answer after reaching 1.0 would be
ignored), so the bounds keep every answer meaningful.
"""

from __future__ import annotations

from app.models.question import QuestionType
from app.practice.ladder import Outcome

P_INIT = 0.2
P_LEARN = 0.15
P_FLOOR = 0.01
P_CEIL = 0.99
SLIP: dict[int, float] = {1: 0.05, 2: 0.08, 3: 0.10, 4: 0.12, 5: 0.15}
GUESS: dict[QuestionType, float] = {
    QuestionType.MULTIPLE_CHOICE: 0.25,
    QuestionType.NUMERIC: 0.05,
    QuestionType.SHORT_TEXT: 0.10,
}


def update(p_known: float, outcome: Outcome, difficulty: int, question_type: QuestionType) -> float:
    """Return the new mastery estimate after one answer.

    Args:
        p_known: Current estimate, 0..1.
        outcome: How the answer went.
        difficulty: Question level 1-5 (sets the slip rate).
        question_type: Sets the guess rate.

    Returns:
        The updated estimate, kept within ``[P_FLOOR, P_CEIL]``.
    """
    slip = SLIP[difficulty]
    guess = GUESS[question_type]
    if outcome is Outcome.CORRECT:
        evidence = p_known * (1 - slip)
        posterior = evidence / (evidence + (1 - p_known) * guess)
    elif outcome is Outcome.INCORRECT:
        evidence = p_known * slip
        posterior = evidence / (evidence + (1 - p_known) * (1 - guess))
    else:
        posterior = p_known
    learned = posterior + (1 - posterior) * P_LEARN
    return min(max(learned, P_FLOOR), P_CEIL)
