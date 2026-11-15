# backend/tests/unit/test_answer_forms.py
"""Maths answer forms and keypad symbols.

Covers:
- LaTeX → plain text: fractions (simple and bracketed parts), roots, braced
  powers, symbols, $ delimiters; plain text unchanged; nesting is bounded
- canonical form: spaces, case, unicode minus, superscripts, "pi" → π, * → ×
- π multiples: kπ, π/n, (kπ)/n, decimals, negatives, ×; not π-free, two π's,
  bad divisor, or non-numeric coefficient
- same_maths: LaTeX key vs typed answer, π-equivalent forms, equal numbers,
  different answers (including the "n instead of π" slip), empty answers
- display_answer wraps bare LaTeX only
- maths vs word answers; every short answer gets every symbol key in a fixed
  order, plus variable letters from maths answers
- word answers keep their symbols (2π cm is not 2 cm; cm² = cm^2; ° = degrees)
- marking short answers: LaTeX keys, π forms, words still loose, display
"""

from fractions import Fraction

import pytest

from app.models.question import QuestionType
from app.questions.answer_forms import (
    KEYPAD_SYMBOLS,
    PI,
    ROOT,
    canonical,
    display_answer,
    is_maths_answer,
    keypad_symbols,
    pi_multiple,
    same_maths,
    tex_to_plain,
)
from app.questions.marking import mark


@pytest.mark.parametrize(
    ("tex", "plain"),
    [
        (r"\frac{1}{2}\pi", f"1/2{PI}"),
        (r"\frac{x+1}{3}", "(x+1)/3"),
        (r"\sqrt{3}", f"{ROOT}3"),
        (r"\sqrt{x+1}", f"{ROOT}(x+1)"),
        ("x^{2}", "x^2"),
        (r"$3 \times 4$", "3 × 4"),
        (r"50\%", "50%"),
        (r"x \leq 3", "x ≤ 3"),
        ("prime", "prime"),
    ],
)
def test_should_rewrite_latex_as_typed_text(tex: str, plain: str) -> None:
    # Act / Assert
    assert tex_to_plain(tex) == plain


def test_should_rewrite_nested_fractions() -> None:
    # Act / Assert
    assert tex_to_plain(r"\frac{\frac{1}{2}}{3}") == "(1/2)/3"


def test_should_build_one_canonical_form() -> None:
    # Act / Assert
    assert canonical(" X² − 1 ") == "x^2-1"
    assert canonical("2 pi") == f"2{PI}"
    assert canonical("3*4") == "3×4"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (f"1/2{PI}", Fraction(1, 2)),
        (f"{PI}/2", Fraction(1, 2)),
        (f"0.5{PI}", Fraction(1, 2)),
        (r"\frac{2\pi}{3}", Fraction(2, 3)),
        (f"(1/2){PI}", Fraction(1, 2)),
        (f"-{PI}", Fraction(-1)),
        (PI, Fraction(1)),
        (f"3×{PI}", Fraction(3)),
        ("2 pi", Fraction(2)),
    ],
)
def test_should_read_multiples_of_pi(answer: str, expected: Fraction) -> None:
    # Act / Assert
    assert pi_multiple(answer) == expected


@pytest.mark.parametrize("answer", ["1/2", f"{PI}{PI}", f"{PI}/0", f"{PI}+1", f"x{PI}", f"2{PI}/x"])
def test_should_not_read_other_answers_as_pi_multiples(answer: str) -> None:
    # Act / Assert
    assert pi_multiple(answer) is None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (f"1/2{PI}", r"\frac{1}{2}\pi"),
        (f"{PI}/2", r"\frac{1}{2}\pi"),
        ("0.5", "1/2"),
        (f"{ROOT}3", r"\sqrt{3}"),
        ("3x + 2", "3x+2"),
    ],
)
def test_should_accept_the_same_maths_in_another_form(given: str, expected: str) -> None:
    # Act / Assert
    assert same_maths(given, expected)


@pytest.mark.parametrize(
    ("given", "expected"),
    [("1/2n", r"\frac{1}{2}\pi"), ("1/2", r"\frac{1}{2}\pi"), ("", "1"), ("3x+2", "2x+3")],
)
def test_should_reject_different_maths(given: str, expected: str) -> None:
    # Act / Assert
    assert not same_maths(given, expected)


def test_should_wrap_bare_latex_for_display_only() -> None:
    # Act / Assert
    assert display_answer(r"\frac{1}{2}\pi") == r"$\frac{1}{2}\pi$"
    assert display_answer(r"$\frac{1}{2}$") == r"$\frac{1}{2}$"
    assert display_answer("prime") == "prime"


@pytest.mark.parametrize(
    ("answer", "maths"),
    [(r"\frac{1}{2}\pi", True), ("2:3", True), ("x = 4", True), ("prime", False), ("", False)],
)
def test_should_tell_maths_answers_from_words(answer: str, maths: bool) -> None:
    # Act / Assert
    assert is_maths_answer(answer) is maths


def test_should_offer_every_symbol_plus_the_letters_the_maths_uses() -> None:
    # Act
    keys = keypad_symbols(["2:3", "y = 2x", r"45^\circ", "prime"])

    # Assert: the full set in a fixed order, then variables (not word letters)
    assert keys == [*KEYPAD_SYMBOLS, "x", "y"]
    assert {PI, ROOT, "²", "°", "≤"} <= set(keys)


def test_should_offer_every_symbol_even_for_word_answers() -> None:
    assert keypad_symbols(["prime number"]) == list(KEYPAD_SYMBOLS)


@pytest.mark.parametrize(
    ("given", "expected", "same"),
    [
        ("2 cm", "2π cm", False),
        ("2pi cm", "2π cm", True),
        ("12 cm^2", "12 cm²", True),
        ("45 degrees", "45°", True),
        ("3 × 4 cm", "3 times 4 cm", True),
    ],
)
def test_word_answers_should_keep_their_symbols(given: str, expected: str, same: bool) -> None:
    # Act
    result = mark(QuestionType.SHORT_TEXT, {"accepted": [expected]}, None, given)

    # Assert
    assert result.correct is same


def test_should_mark_a_typed_pi_answer_against_a_latex_key() -> None:
    # Arrange
    key = {"accepted": [r"\frac{1}{2}\pi"]}

    # Act
    right = mark(QuestionType.SHORT_TEXT, key, None, f"{PI}/2")
    slip = mark(QuestionType.SHORT_TEXT, key, None, "1/2n")

    # Assert
    assert right.correct
    assert not slip.correct
    assert right.correct_answer_display == r"$\frac{1}{2}\pi$"


def test_should_still_mark_word_answers_loosely() -> None:
    # Act
    result = mark(QuestionType.SHORT_TEXT, {"accepted": ["prime number"]}, None, "Prime-number!")

    # Assert
    assert result.correct
