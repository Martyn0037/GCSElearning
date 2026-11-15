# backend/tests/unit/test_keyboards.py
"""On-screen keys by subject.

Covers:
- Spanish and French: their accented letters and punctuation, no number pad,
  phone keyboard kept, for short and written answers alike
- other non-maths subjects (English, history, ...): no keys
- maths and sciences: numbers get the number pad as the keyboard; maths short
  answers replace the keyboard; word short answers keep it with every symbol;
  written answers get numbers and symbols below the keyboard
- unknown subject: the maths keys (every key, the safe default)
- multiple choice: no keys in any subject
"""

from __future__ import annotations

from typing import Any

import pytest

from app.models.question import Question, QuestionType
from app.questions.answer_forms import KEYPAD_SYMBOLS
from app.questions.keyboards import LANGUAGE_KEYS, Keys, keys_for


def _question(question_type: QuestionType, answer: dict[str, Any] | None = None) -> Question:
    return Question(question_type=question_type, answer=answer or {})


@pytest.mark.parametrize("slug", ["spanish", "french"])
@pytest.mark.parametrize("question_type", [QuestionType.SHORT_TEXT, QuestionType.EXTENDED])
def test_languages_should_get_their_accented_letters_only(
    slug: str, question_type: QuestionType
) -> None:
    # Act
    keys = keys_for(_question(question_type, {"accepted": ["el niño"]}), slug)

    # Assert
    assert keys == Keys(keypad=False, number_keys=False, symbol_keys=list(LANGUAGE_KEYS[slug]))


def test_spanish_keys_should_include_n_tilde_and_inverted_marks() -> None:
    assert {"ñ", "á", "é", "í", "ó", "ú", "ü", "¿", "¡"} <= set(LANGUAGE_KEYS["spanish"])
    assert {"ç", "é", "è", "à", "œ"} <= set(LANGUAGE_KEYS["french"])


@pytest.mark.parametrize(
    "slug", ["english-literature", "history", "geography", "religious-studies"]
)
def test_other_word_subjects_should_get_no_keys(slug: str) -> None:
    keys = keys_for(_question(QuestionType.SHORT_TEXT, {"accepted": ["Macbeth"]}), slug)

    assert keys == Keys(keypad=False, number_keys=False, symbol_keys=[])


@pytest.mark.parametrize("slug", ["maths", "physics", None])
def test_numeric_answers_should_use_the_number_pad_as_the_keyboard(slug: str | None) -> None:
    keys = keys_for(_question(QuestionType.NUMERIC, {"value": 3}), slug)

    assert keys == Keys(keypad=True, number_keys=True, symbol_keys=[])


def test_maths_short_answers_should_replace_the_keyboard_with_every_symbol() -> None:
    keys = keys_for(_question(QuestionType.SHORT_TEXT, {"accepted": ["2x+3"]}), "maths")

    assert keys.keypad is True
    assert keys.number_keys is True
    assert keys.symbol_keys == [*KEYPAD_SYMBOLS, "x"]


def test_science_word_answers_should_keep_the_keyboard_with_keys_below() -> None:
    keys = keys_for(_question(QuestionType.SHORT_TEXT, {"accepted": ["osmosis"]}), "biology")

    assert (keys.keypad, keys.number_keys) == (False, True)
    assert keys.symbol_keys == list(KEYPAD_SYMBOLS)


def test_maths_written_answers_should_get_numbers_and_symbols_below_the_keyboard() -> None:
    keys = keys_for(_question(QuestionType.EXTENDED), "chemistry")

    assert keys == Keys(keypad=False, number_keys=True, symbol_keys=list(KEYPAD_SYMBOLS))


@pytest.mark.parametrize("slug", ["maths", "spanish", "history", None])
def test_multiple_choice_should_never_get_keys(slug: str | None) -> None:
    keys = keys_for(_question(QuestionType.MULTIPLE_CHOICE), slug)

    assert keys == Keys(keypad=False, number_keys=False, symbol_keys=[])
