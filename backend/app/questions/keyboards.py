# backend/app/questions/keyboards.py
"""Which on-screen keys a question gets, by subject.

- Maths and the sciences: the number pad plus maths symbols (π, √, ², ...).
- Spanish and French: that language's accented letters and punctuation, so
  "ñ" or "ç" never depends on knowing a phone's long-press. No number pad.
- Every other subject (English, history, ...): no keys; the phone keyboard
  has everything needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.question import Question, QuestionType
from app.questions.answer_forms import is_maths_answer, keypad_symbols

# Subjects whose answers can be numbers or maths. Also decides question types.
QUANTITATIVE_SUBJECTS = frozenset(
    {"maths", "combined-science", "biology", "chemistry", "physics", "computer-science"}
)

# Lower case only: capitals at the start of a sentence come from the phone's
# shift key, and the marker ignores case.
LANGUAGE_KEYS: dict[str, tuple[str, ...]] = {
    "spanish": ("á", "é", "í", "ó", "ú", "ü", "ñ", "¿", "¡"),
    "french": ("é", "è", "ê", "ë", "à", "â", "ç", "î", "ï", "ô", "ù", "û", "œ", "«", "»"),
}


@dataclass(frozen=True, slots=True)
class Keys:
    """The keys for one question.

    Attributes:
        keypad: The answer is maths: the keys replace the phone keyboard.
        number_keys: Show the number pad.
        symbol_keys: Extra keys (maths symbols or accented letters), in order.
    """

    keypad: bool
    number_keys: bool
    symbol_keys: list[str]


NO_KEYS = Keys(keypad=False, number_keys=False, symbol_keys=[])


def keys_for(question: Question, subject_slug: str | None) -> Keys:
    """The on-screen keys for a question in a subject.

    Args:
        question: The question being served.
        subject_slug: Its subject (``None`` if unknown: treated as maths, the
            safest default since it offers every key).

    Returns:
        Which keys to show. Multiple choice needs none.
    """
    if question.question_type is QuestionType.MULTIPLE_CHOICE:
        return NO_KEYS
    if subject_slug in LANGUAGE_KEYS:
        return Keys(keypad=False, number_keys=False, symbol_keys=list(LANGUAGE_KEYS[subject_slug]))
    if subject_slug is not None and subject_slug not in QUANTITATIVE_SUBJECTS:
        return NO_KEYS
    return _maths_keys(question)


def _maths_keys(question: Question) -> Keys:
    if question.question_type is QuestionType.NUMERIC:
        return Keys(keypad=True, number_keys=True, symbol_keys=[])
    if question.question_type is QuestionType.EXTENDED:
        return Keys(keypad=False, number_keys=True, symbol_keys=keypad_symbols([]))
    if question.question_type is QuestionType.SHORT_TEXT:
        accepted = [str(a) for a in question.answer.get("accepted", [])]
        maths = bool(accepted) and all(is_maths_answer(a) for a in accepted)
        return Keys(keypad=maths, number_keys=True, symbol_keys=keypad_symbols(accepted))
    return NO_KEYS
