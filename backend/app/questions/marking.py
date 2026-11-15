# backend/app/questions/marking.py
"""Deterministic marking for multiple-choice, numeric and short-text answers.

No AI is involved: student answers are compared with the stored key.
Maths short answers are compared via ``app.questions.answer_forms``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from app.models.question import QuestionType
from app.questions.answer_forms import display_answer, is_maths_answer, same_maths

MAX_ANSWER_LENGTH = 200

_NUMBER = re.compile(
    r"^\s*(?P<num>[-+\u2212]?\s*(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:\s*/\s*\d+)?)\s*(?P<unit>[^\d\s].*)?$"
)


def parse_number(raw: str) -> Fraction | None:
    """Parse a student's number: integers, decimals, ``7/2``, thousands commas, unicode minus.

    Returns:
        The exact value, or ``None`` if it isn't a number.
    """
    # Accept the unicode minus sign that phone keyboards sometimes insert.
    text = raw.strip().replace("\u2212", "-").replace(" ", "")
    if not text or len(text) > 40:
        return None
    try:
        if "/" in text:
            top, bottom = text.split("/", 1)
            denominator = Fraction(Decimal(bottom))
            if denominator == 0:
                return None
            return Fraction(Decimal(top.replace(",", ""))) / denominator
        return Fraction(Decimal(text.replace(",", "")))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def split_number_and_unit(raw: str) -> tuple[Fraction | None, str | None]:
    """Split ``"3.5 cm"`` into (7/2, "cm"); the unit is ``None`` when absent."""
    match = _NUMBER.match(raw)
    if not match:
        return None, None
    unit = match.group("unit")
    return parse_number(match.group("num")), unit.strip() if unit else None


# Symbols spelled out before accents are dropped, so "2π cm" never matches "2 cm".
_SYMBOL_WORDS = {
    "\u03c0": " pi ",
    "\u221a": " root ",
    "\u00b2": " ^2 ",
    "\u00b3": " ^3 ",
    "^": " pow ",
    "\u00b0": " degrees ",
    "\u00d7": " times ",
    "\u00f7": " divide ",
    "\u2264": " le ",
    "\u2265": " ge ",
    "<": " lt ",
    ">": " gt ",
    "%": " percent ",
}


def normalise_text(value: str) -> str:
    """Case-, accent-, punctuation- and spacing-insensitive form for comparing words.

    Maths symbols are spelled out rather than dropped, so they still count.
    """
    for symbol, word in _SYMBOL_WORDS.items():
        value = value.replace(symbol, word)
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    spaced = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", folded)  # "2pi" = "2 pi"
    return " ".join(re.sub(r"[^\w\s]", " ", spaced).split())


def _unit_matches(given: str | None, expected: str | None) -> bool:
    if given is None or expected is None:
        return True  # a missing unit isn't penalised in practice mode
    return normalise_text(given) == normalise_text(expected)


@dataclass(frozen=True, slots=True)
class MarkResult:
    """Whether an answer earned the marks, and the correct answer to show."""

    correct: bool
    correct_answer_display: str


def mark(
    question_type: QuestionType,
    answer_key: dict[str, Any],
    options: list[dict[str, str]] | None,
    response: str,
) -> MarkResult:
    """Mark one response against a question's key.

    Args:
        question_type: How to mark.
        answer_key: The stored key (see ``Question.answer``).
        options: Multiple-choice options, for showing the correct text.
        response: What the student submitted (already length-limited).

    Returns:
        The result.
    """
    if question_type is QuestionType.MULTIPLE_CHOICE:
        correct_label = str(answer_key["correct_option"])
        text = next((o["text"] for o in options or [] if o["label"] == correct_label), "")
        return MarkResult(response.strip().upper() == correct_label, f"{correct_label}: {text}")

    if question_type is QuestionType.NUMERIC:
        expected = Fraction(Decimal(str(answer_key["value"])))
        tolerance = Fraction(Decimal(str(answer_key.get("tolerance") or "0")))
        unit = answer_key.get("unit")
        given, given_unit = split_number_and_unit(response)
        display = f"{answer_key['value']}{' ' + unit if unit else ''}"
        ok = (
            given is not None
            and abs(given - expected) <= tolerance
            and _unit_matches(given_unit, unit)
        )
        return MarkResult(ok, display)

    accepted = [str(a) for a in answer_key.get("accepted", [])]
    # Words compare loosely (case, accents, punctuation); maths answers compare
    # by form and value, so symbols like π and "/" aren't thrown away.
    ok = any(
        same_maths(response, a)
        if is_maths_answer(a)
        else normalise_text(response) == normalise_text(a)
        for a in accepted
    )
    return MarkResult(ok, display_answer(accepted[0]) if accepted else "")
