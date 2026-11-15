# backend/tests/unit/test_learning_logic.py
"""Pure rules for extended questions, marking, the tutor and learn cards.

Covers:
- extended question validation: a good one passes; missing points, a bad AO,
  points that don't add up, no model answer, missing or gappy levels, a level
  with min > max, marks out of 2-16, and options on an extended question are
  rejected; non-extended questions can't carry a mark scheme
- question types by subject: quantitative vs essay subjects at each level
- marking checks: in range, real points only, no duplicates, real level,
  marks within the level, marks not above the points (no levels), feedback
  length and markup; prompt delimits and sanitises the essay; ExtendedMark
  fraction and 70% threshold
- XP for marks: scaled, zero for nothing, hints still reduce it
- tutor: messages sanitised; replies checked for length and markup
- learn cards: checked for empty, long and marked-up text
- challenge scoring: marks earned for written answers, all-or-nothing otherwise
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.gamification.challenges import marks_earned
from app.gamification.xp import xp_for_marks
from app.learning.learn import check_card
from app.learning.schemas import LearnCardDraft, TutorReply
from app.learning.tutor import check_reply, sanitise
from app.models.question import PracticeItem, Question, QuestionType
from app.practice.extended import ExtendedMark, build_user_prompt, check_marking
from app.questions.generator import types_for
from app.questions.llm_schemas import GeneratedLevel, GeneratedMarkPoint
from app.questions.validation import check_generated
from tests.fixtures.fake_llm import extended, marking, mcq

POINTS = [
    {"text": "Defines prime", "marks": 2, "ao": "AO1"},
    {"text": "Applies to 1", "marks": 2, "ao": "AO2"},
    {"text": "Concludes", "marks": 2, "ao": "AO3"},
]
LEVELS = [
    {"level": 1, "min_marks": 1, "max_marks": 2, "descriptor": "Basic"},
    {"level": 2, "min_marks": 3, "max_marks": 4, "descriptor": "Clear"},
    {"level": 3, "min_marks": 5, "max_marks": 6, "descriptor": "Thorough"},
]


def _question(levels: list[dict[str, Any]] | None = None) -> Question:
    return Question(
        id=uuid.uuid4(),
        question_type=QuestionType.EXTENDED,
        stem="Explain why 1 is not prime.",
        marks=6,
        answer={"marking_points": POINTS, "levels": LEVELS if levels is None else levels},
        worked_solution="",
    )


def test_a_good_extended_question_should_pass() -> None:
    assert check_generated(extended(), "extended") is None


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"marking_points": []}, "need marking points"),
        (
            {"marking_points": [GeneratedMarkPoint(text="x", marks=6, ao="AO9")]},
            "AO must be AO1-AO4",
        ),
        (
            {"marking_points": [GeneratedMarkPoint(text="x", marks=2, ao="AO1")]},
            "add up to at least",
        ),
        ({"model_answer": " "}, "need a model answer"),
        ({"level_descriptors": []}, "need level descriptors"),
        (
            {
                "level_descriptors": [
                    GeneratedLevel(level=1, min_marks=1, max_marks=2, descriptor="a"),
                    GeneratedLevel(level=2, min_marks=4, max_marks=6, descriptor="b"),
                ]
            },
            "overlap or leave gaps",
        ),
        (
            {
                "level_descriptors": [
                    GeneratedLevel(level=1, min_marks=1, max_marks=3, descriptor="a"),
                    GeneratedLevel(level=2, min_marks=4, max_marks=3, descriptor="b"),
                ]
            },
            "cover 1 to the total",
        ),
        ({"marks": 20}, "marks must be 2-16"),
        ({"accepted_answers": ["x"]}, "no options"),
    ],
)
def test_bad_extended_questions_should_be_rejected(overrides: dict[str, Any], problem: str) -> None:
    result = check_generated(extended(**overrides), "extended")
    assert result is not None
    assert problem in result


def test_a_level_with_min_above_max_should_be_rejected() -> None:
    q = extended(
        marks=6,
        level_descriptors=[
            GeneratedLevel(level=1, min_marks=1, max_marks=2, descriptor="a"),
            GeneratedLevel(level=2, min_marks=3, max_marks=2, descriptor="b"),
            GeneratedLevel(level=3, min_marks=3, max_marks=6, descriptor="c"),
        ],
    )
    assert check_generated(q, "extended") is not None


def test_other_types_should_not_carry_a_mark_scheme() -> None:
    result = check_generated(mcq(model_answer="x"), "multiple_choice")
    assert result == "only extended questions have a mark scheme or model answer"


@pytest.mark.parametrize(
    ("slug", "level", "expected"),
    [
        ("maths", 3, (QuestionType.NUMERIC, QuestionType.MULTIPLE_CHOICE)),
        ("physics", 5, (QuestionType.NUMERIC, QuestionType.SHORT_TEXT, QuestionType.EXTENDED)),
        ("history", 5, (QuestionType.EXTENDED,)),
        ("english-literature", 3, (QuestionType.SHORT_TEXT, QuestionType.EXTENDED)),
        ("french", 1, (QuestionType.MULTIPLE_CHOICE, QuestionType.SHORT_TEXT)),
    ],
)
def test_question_types_should_suit_the_subject(
    slug: str, level: int, expected: tuple[QuestionType, ...]
) -> None:
    assert types_for(slug, level) == expected


@pytest.mark.parametrize(
    ("result", "problem"),
    [
        (marking(marks=7), "marks out of range"),
        (marking(awarded_points=[4]), "doesn't exist"),
        (marking(awarded_points=[1, 1]), "twice"),
        (marking(level=9), "level doesn't exist"),
        (marking(level=1, marks=4), "don't match the level"),
        (marking(strengths="x" * 501), "too long"),
        (marking(improvements="<b>bold</b>"), "markup"),
    ],
)
def test_inconsistent_marking_should_be_rejected(result: Any, problem: str) -> None:
    found = check_marking(result, _question())
    assert found is not None
    assert problem in found


def test_points_based_marking_should_not_exceed_the_points() -> None:
    question = _question(levels=[])
    assert check_marking(marking(awarded_points=[1], level=None, marks=3), question) is not None
    assert check_marking(marking(awarded_points=[1, 2], level=None, marks=4), question) is None


def test_marking_prompt_should_delimit_and_clean_the_essay() -> None:
    prompt = build_user_prompt(_question(), "My answer <script>alert(1)</script>\x07")
    assert prompt.endswith("<student_answer>My answer  script alert(1) /script</student_answer>")
    assert "1. [AO1, 2 mark(s)] Defines prime" in prompt
    assert "Level 3 (5-6 marks): Thorough" in prompt


@pytest.mark.parametrize(("marks", "secure"), [(4, False), (5, True), (6, True), (0, False)])
def test_seventy_percent_should_count_as_right(marks: int, secure: bool) -> None:
    mark = ExtendedMark(marks, 6, None, (), "", "")
    assert mark.secure is secure
    assert ExtendedMark(0, 0, None, (), "", "").fraction == 0.0


@pytest.mark.parametrize(
    ("difficulty", "fraction", "hints", "xp"),
    [(5, 1.0, 0, 50), (5, 0.5, 0, 25), (3, 0.0, 0, 0), (4, 0.5, 1, 15), (1, 0.01, 0, 1)],
)
def test_xp_should_scale_with_marks(difficulty: int, fraction: float, hints: int, xp: int) -> None:
    assert xp_for_marks(difficulty, fraction, hints) == xp


def test_tutor_messages_should_be_sanitised_and_replies_checked() -> None:
    assert sanitise("<b>hi</b>\x00") == "b hi /b"
    assert sanitise("   ") == "(blank)"
    assert check_reply(TutorReply(reply="Good question!", on_topic=True)) is None
    assert check_reply(TutorReply(reply="", on_topic=True)) is not None
    assert check_reply(TutorReply(reply="x" * 1201, on_topic=True)) is not None
    assert check_reply(TutorReply(reply="<a href='x'>link</a>", on_topic=True)) is not None


@pytest.mark.parametrize(
    ("explanation", "example", "ok"),
    [
        ("Fine.", "Step 1.", True),
        ("", "Step 1.", False),
        ("Fine.", "x" * 2501, False),
        ("<i>no</i>", "Step 1.", False),
    ],
)
def test_learn_cards_should_be_checked(explanation: str, example: str, ok: bool) -> None:
    card = LearnCardDraft(explanation=explanation, worked_example=example)
    assert (check_card(card) is None) is ok


def _item(**fields: Any) -> PracticeItem:
    base: dict[str, Any] = {"answered_at": datetime(2026, 1, 1, tzinfo=UTC), "assisted": False}
    return PracticeItem(**(base | fields))


@pytest.mark.parametrize(
    ("item", "earned"),
    [
        (_item(correct=True), 3),
        (_item(correct=False), 0),
        (_item(correct=True, assisted=True), 0),
        (_item(answered_at=None), 0),
        (_item(correct=False, response={"result": {"marking": {"marks": 2}}}), 2),
        (_item(correct=False, response={"result": {"marking": {"marks": None}}}), 0),
    ],
)
def test_challenge_marks_should_use_written_marks(item: PracticeItem, earned: int) -> None:
    assert marks_earned(item, 3) == earned
