# backend/tests/unit/test_questions_logic.py
"""Unit tests for marking, validation, the ladder, SymPy checks and the go-live decision.

Covers:
- numbers: integers, decimals, fractions, commas, unicode minus, junk, /0
- marking: MCQ case-insensitive; numeric tolerance, units (right/wrong/absent);
  short text normalised
- validation: each rule (type, command word, marks, hints, HTML, MCQ/numeric/
  short-text fields, hints giving away the answer)
- ladder: up on 3-in-a-row and 4-of-5, down on 2 misses, assisted neither,
  limits at levels 1 and 5
- SymPy: allowlist, isolated evaluation, match/mismatch/unchecked, timeout
- decide: every failing check rejects; strict mode -> pending review; the
  verifier's answer is read from forms like "450 (option C)" or "b = 11 (...)"
  without matching numbers in its working
- the verification prompt treats hint 4 as the full solution, not a leak
- prompts contain the objective and no placeholders; scheduler intervals
"""

from __future__ import annotations

from datetime import timedelta
from fractions import Fraction
from typing import Any

import pytest

from app.models.curriculum import Tier
from app.models.question import QuestionStatus, QuestionType
from app.practice.ladder import LadderState, Outcome, advance
from app.questions.generator import decide
from app.questions.marking import mark, parse_number, split_number_and_unit
from app.questions.prompts import VERIFICATION_SYSTEM, ObjectiveContext, generation_user_prompt
from app.questions.sympy_check import (
    CheckOutcome,
    check_numeric_answer,
    evaluate,
    is_safe_expression,
)
from app.questions.validation import check_generated
from app.worker import Scheduler
from tests.fixtures.factories import FIXED_NOW, make_settings
from tests.fixtures.fake_llm import mcq, numeric, short_text, verification

C, X, A = Outcome.CORRECT, Outcome.INCORRECT, Outcome.ASSISTED  # correct, wrong, assisted


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("42", Fraction(42)),
        ("-3.5", Fraction(-7, 2)),
        ("\u22123.5", Fraction(-7, 2)),  # unicode minus
        ("7/2", Fraction(7, 2)),
        ("1,250", Fraction(1250)),
        (" 0.375 ", Fraction(3, 8)),
        ("abc", None),
        ("1/0", None),
        ("", None),
    ],
)
def test_parse_number(raw: str, expected: Fraction | None) -> None:
    assert parse_number(raw) == expected


def test_split_number_and_unit() -> None:
    assert split_number_and_unit("3.5 cm") == (Fraction(7, 2), "cm")
    assert split_number_and_unit("12") == (Fraction(12), None)


MCQ_OPTIONS = [{"label": "C", "text": "6"}]


@pytest.mark.parametrize(
    ("qtype", "key", "response", "correct"),
    [
        (QuestionType.MULTIPLE_CHOICE, {"correct_option": "C"}, " c ", True),
        (QuestionType.MULTIPLE_CHOICE, {"correct_option": "C"}, "B", False),
        (QuestionType.NUMERIC, {"value": "4.75", "tolerance": "0"}, "19/4", True),
        (QuestionType.NUMERIC, {"value": "4.75", "tolerance": "0"}, "4.7", False),
        (QuestionType.NUMERIC, {"value": "28.27", "tolerance": "0.01"}, "28.274", True),
        (QuestionType.NUMERIC, {"value": "5", "tolerance": "0", "unit": "cm"}, "5 cm", True),
        (QuestionType.NUMERIC, {"value": "5", "tolerance": "0", "unit": "cm"}, "5", True),
        (QuestionType.NUMERIC, {"value": "5", "tolerance": "0", "unit": "cm"}, "5 kg", False),
        (QuestionType.NUMERIC, {"value": "5", "tolerance": "0"}, "five", False),
        (QuestionType.SHORT_TEXT, {"accepted": ["prime number"]}, "Prime   Number!", True),
        (QuestionType.SHORT_TEXT, {"accepted": ["prime number"]}, "composite", False),
    ],
)
def test_mark(qtype: QuestionType, key: dict[str, Any], response: str, correct: bool) -> None:
    assert mark(qtype, key, MCQ_OPTIONS, response).correct is correct


def test_mark_should_show_correct_answer() -> None:
    assert (
        mark(
            QuestionType.MULTIPLE_CHOICE, {"correct_option": "C"}, MCQ_OPTIONS, "A"
        ).correct_answer_display
        == "C: 6"
    )
    assert (
        mark(QuestionType.NUMERIC, {"value": "5", "unit": "cm"}, None, "1").correct_answer_display
        == "5 cm"
    )


@pytest.mark.parametrize(
    "question", [mcq(), numeric(), short_text()], ids=["mcq", "numeric", "short"]
)
def test_valid_questions_should_pass(question: Any) -> None:
    assert check_generated(question, question.question_type) is None


@pytest.mark.parametrize(
    ("question", "expected_type", "problem"),
    [
        (mcq(), "numeric", "expected a numeric"),
        (mcq(command_word="Ponder"), "multiple_choice", "command word"),
        (mcq(marks=9), "multiple_choice", "marks"),
        (mcq(hints=["a", "b", "c"]), "multiple_choice", "four non-empty hints"),
        (mcq(stem="<script>alert(1)</script>"), "multiple_choice", "HTML"),
        (mcq(correct_option="E"), "multiple_choice", "correct_option"),
        (mcq(options=mcq().options[:3]), "multiple_choice", "options A-D"),
        (numeric(numeric_answer="four"), "numeric", "plain numbers"),
        (numeric(numeric_tolerance="-1"), "numeric", "negative"),
        (short_text(accepted_answers=[]), "short_text", "accepted_answers"),
        (numeric(hints=["Try 4.75", "b", "c", "d"]), "numeric", "give away"),
        (short_text(hints=["It's prime", "b", "c", "d"]), "short_text", "give away"),
    ],
    ids=[
        "wrong_type",
        "command_word",
        "marks",
        "hint_count",
        "html",
        "bad_correct_option",
        "three_options",
        "numeric_not_number",
        "negative_tolerance",
        "no_accepted",
        "numeric_leak",
        "text_leak",
    ],
)
def test_invalid_questions_should_be_rejected(
    question: Any, expected_type: str, problem: str
) -> None:
    result = check_generated(question, expected_type)

    assert result is not None
    assert problem in result


def test_numeric_leak_check_should_not_match_inside_other_numbers() -> None:
    question = numeric(
        numeric_answer="5", check_expression="5", hints=["Add 15 to it", "b", "c", "d"]
    )

    assert check_generated(question, "numeric") is None


@pytest.mark.parametrize(
    ("start", "outcomes", "expected_level"),
    [
        (1, [C, C, C], 2),
        (1, [C, X, C, C, C], 2),  # 3 in a row
        (2, [C, C, X, C, C], 3),  # 4 of last 5
        (3, [X, X], 2),
        (3, [X, C, X], 3),  # misses not consecutive
        (3, [C, C, A, C], 3),  # assisted breaks the run
        (3, [A, A, A], 3),  # assisted never drops
        (5, [C, C, C], 5),
        (1, [X, X, X], 1),
    ],
    ids=[
        "three_in_row",
        "run_after_miss",
        "four_of_five",
        "two_misses",
        "non_consecutive",
        "assisted_breaks_run",
        "assisted_no_drop",
        "max_level",
        "min_level",
    ],
)
def test_ladder(start: int, outcomes: list[Outcome], expected_level: int) -> None:
    state = LadderState(start)
    for outcome in outcomes:
        state = advance(state, outcome)

    assert state.level == expected_level


def test_ladder_should_reset_history_on_level_change() -> None:
    assert advance(LadderState(1, (C, C)), C) == LadderState(2)


@pytest.mark.parametrize(
    ("expression", "safe"),
    [
        ("7/2 + 1.25", True),
        ("pi*3^2", True),
        ("sqrt(2)", True),
        ("__import__('os')", False),
        ("x+1", False),
        ("", False),
    ],
)
def test_expression_allowlist(expression: str, safe: bool) -> None:
    assert is_safe_expression(expression) is safe


async def test_sympy_should_evaluate_exactly() -> None:
    assert await evaluate("7/2 + 1.25") == Fraction(19, 4)


@pytest.mark.parametrize(
    ("expression", "expected", "tolerance", "outcome"),
    [
        ("7/2", "3.5", "0", CheckOutcome.MATCH),
        ("pi*3^2", "28.27", "0.01", CheckOutcome.MATCH),
        ("7/3", "3.5", "0", CheckOutcome.MISMATCH),
        (None, "3.5", "0", CheckOutcome.UNCHECKED),
        ("import os", "3.5", "0", CheckOutcome.UNCHECKED),
    ],
)
async def test_numeric_check(
    expression: str | None, expected: str, tolerance: str, outcome: CheckOutcome
) -> None:
    result = await check_numeric_answer(expression, Fraction(expected), Fraction(tolerance))

    assert result is outcome


async def test_sympy_should_time_out_on_huge_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.questions.sympy_check.EVAL_TIMEOUT_SECONDS", 0.5)

    assert await evaluate("9^9^9^9") is None


SETTINGS = make_settings()


def test_decide_should_activate_when_everything_passes() -> None:
    decision = decide(mcq(), verification(), CheckOutcome.UNCHECKED, SETTINGS)

    assert (decision.status, decision.verified) == (QuestionStatus.ACTIVE, True)


@pytest.mark.parametrize(
    ("question", "check", "sympy", "reason"),
    [
        (mcq(), verification(answer_is_correct=False), CheckOutcome.UNCHECKED, "key is wrong"),
        (mcq(), verification(solved_answer="B"), CheckOutcome.UNCHECKED, "differs from the key"),
        (
            mcq(),
            verification(within_objective=False),
            CheckOutcome.UNCHECKED,
            "outside the objective",
        ),
        (mcq(), verification(suitable_for_tier=False), CheckOutcome.UNCHECKED, "tier"),
        (mcq(), verification(hints_reveal_answer_early=True), CheckOutcome.UNCHECKED, "hints"),
        (mcq(), verification(mark_scheme_consistent=False), CheckOutcome.UNCHECKED, "mark scheme"),
        (mcq(), verification(confidence=0.5), CheckOutcome.UNCHECKED, "confidence"),
        (numeric(), verification(solved_answer="4.75"), CheckOutcome.MISMATCH, "SymPy"),
        (numeric(), verification(solved_answer="4.8"), CheckOutcome.MATCH, "differs"),
        (short_text(), verification(solved_answer="even"), CheckOutcome.UNCHECKED, "differs"),
    ],
)
def test_decide_should_reject_failures(
    question: Any, check: Any, sympy: CheckOutcome, reason: str
) -> None:
    decision = decide(question, check, sympy, SETTINGS)

    assert decision.status is QuestionStatus.REJECTED
    assert reason in decision.notes


@pytest.mark.parametrize(
    ("question", "solved"),
    [
        (numeric(), "4.75 exactly"),
        (numeric(), "x = 4.75 (because 19/4 = 4.75)"),
        (numeric(), "19/4"),
        (mcq(), "c"),
        (mcq(), "C)"),
        (mcq(), "450 (option C)"),
        (mcq(), "The answer is C"),
        (short_text(), "Prime number"),
        (short_text(), "prime (it has exactly two factors)"),
    ],
)
def test_decide_should_accept_verifier_answers_in_other_forms(question: Any, solved: str) -> None:
    sympy = CheckOutcome.MATCH if question.question_type == "numeric" else CheckOutcome.UNCHECKED

    assert decide(question, verification(solved_answer=solved), sympy, SETTINGS).verified


@pytest.mark.parametrize(
    ("question", "solved"),
    [
        (numeric(), "b = 11 (because 27/99 = 4.75)"),
        (mcq(), "450 (option B)"),
        (mcq(), "450"),
    ],
)
def test_decide_should_not_be_fooled_by_numbers_in_working(question: Any, solved: str) -> None:
    sympy = CheckOutcome.MATCH if question.question_type == "numeric" else CheckOutcome.UNCHECKED

    decision = decide(question, verification(solved_answer=solved), sympy, SETTINGS)

    assert "differs from the key" in decision.notes


def test_verification_prompt_should_say_the_last_hint_is_the_full_solution() -> None:
    assert "hint 4 is deliberately the full worked solution" in VERIFICATION_SYSTEM
    assert "only if hint 1, 2 or 3" in VERIFICATION_SYSTEM


def test_decide_should_hold_for_review_in_strict_mode() -> None:
    decision = decide(
        mcq(), verification(), CheckOutcome.UNCHECKED, make_settings(question_strict_mode=True)
    )

    assert decision.status is QuestionStatus.PENDING_REVIEW


def test_generation_prompt_should_contain_objective_and_avoid_list() -> None:
    ctx = ObjectiveContext(
        subject="Mathematics",
        board="Pearson Edexcel",
        spec_code="1MA1",
        spec_version="Issue 2",
        topic="Number",
        subtopic="Structure and calculation",
        objective_ref="N4",
        objective_text="use the concepts of prime numbers",
        keywords=("prime numbers",),
        out_of_scope=None,
        tier=Tier.HIGHER,
    )

    prompt = generation_user_prompt(ctx, 3, "numeric", ["An old question"])

    assert "Objective N4: use the concepts of prime numbers" in prompt
    assert "Tier: Higher." in prompt
    assert "Difficulty level 3: Apply" in prompt
    assert "- An old question" in prompt


def test_scheduler_should_run_each_job_once_per_interval() -> None:
    scheduler = Scheduler()

    first = scheduler.due(FIXED_NOW)
    soon = scheduler.due(FIXED_NOW + timedelta(minutes=5))
    later = scheduler.due(FIXED_NOW + timedelta(minutes=11))

    assert set(first) == {"top_up_bank", "purge_rate_limits"}
    assert soon == []
    assert later == ["top_up_bank"]
