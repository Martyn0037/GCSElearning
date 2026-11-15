# backend/app/practice/items.py
"""Shared practice helpers: the question as the student sees it, and access checks.

Used by topic practice, reviews and challenges alike.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.curriculum import LearningObjective, Topic
from app.models.enrolment import StudentSubject
from app.models.question import Hint, PracticeItem, Question, QuestionType
from app.practice.schemas import OptionOut, PracticeItemOut
from app.questions.answer_forms import is_maths_answer, keypad_symbols

MAX_HINT_LEVEL = 4


async def load_enrolment(
    session: AsyncSession,
    student_id: uuid.UUID,
    enrolment_id: uuid.UUID,
    *,
    lock: bool = False,
) -> StudentSubject:
    """The student's own, ready subject.

    Raises:
        NotFoundError: Unknown or someone else's subject.
        ConflictError: ``SUBJECT_NOT_READY`` while it has no spec.
    """
    enrolment = await session.get(StudentSubject, enrolment_id, with_for_update=lock)
    if enrolment is None or enrolment.student_id != student_id:
        raise NotFoundError("Subject not found")
    if enrolment.specification_id is None:
        raise ConflictError("This subject is still being set up.", code="SUBJECT_NOT_READY")
    return enrolment


async def require_unlocked_topic(
    session: AsyncSession, enrolment: StudentSubject, topic_id: uuid.UUID
) -> Topic:
    """The topic, if it's a current topic in the subject's spec.

    Every topic is open (ADR-021); "covered at school" is only a label.

    Raises:
        NotFoundError: Not a current topic of this subject.
    """
    topic = await session.get(Topic, topic_id)
    if topic is None or topic.specification_id != enrolment.specification_id or topic.retired_at:
        raise NotFoundError("Topic not found")
    return topic


async def item_out(
    session: AsyncSession, item: PracticeItem, question: Question | None = None
) -> PracticeItemOut:
    """A practice item as the student sees it: never includes the answer."""
    question = question or await session.get(Question, item.question_id)
    assert question is not None  # noqa: S101 - FK guarantees it
    objective_ref = await session.scalar(
        select(LearningObjective.ref).where(LearningObjective.id == question.objective_id)
    )
    hints = (
        await session.scalars(
            select(Hint.text)
            .where(Hint.question_id == question.id, Hint.level <= item.hints_revealed)
            .order_by(Hint.level)
        )
    ).all()
    return PracticeItemOut(
        id=item.id,
        question_type=question.question_type,
        command_word=question.command_word,
        stem=question.stem,
        options=[OptionOut(**o) for o in question.options or []],
        unit=question.answer.get("unit") if question.question_type.value == "numeric" else None,
        marks=question.marks,
        difficulty=item.difficulty,
        objective_ref=objective_ref or "",
        hints=list(hints),
        hints_remaining=MAX_HINT_LEVEL - item.hints_revealed,
        review=item.mistake_id is not None,
        **_keypad(question),
    )


def _keypad(question: Question) -> dict[str, Any]:
    """How the on-screen keys appear for this question.

    Every typed answer gets keys, so no number or symbol is ever out of reach:
    numbers get the number keys; every short answer also gets the full symbol
    set (π, √, powers, °, ...). ``keypad`` is true when the answer is maths,
    so the keys replace the phone keyboard; for word answers the keyboard
    stays and the keys sit underneath. Multiple choice needs no typing.
    """
    if question.question_type is QuestionType.NUMERIC:
        return {"keypad": True, "symbol_keys": []}
    if question.question_type is QuestionType.EXTENDED:
        return {"keypad": False, "symbol_keys": keypad_symbols([])}
    if question.question_type is QuestionType.SHORT_TEXT:
        accepted = [str(a) for a in question.answer.get("accepted", [])]
        maths = bool(accepted) and all(is_maths_answer(a) for a in accepted)
        return {"keypad": maths, "symbol_keys": keypad_symbols(accepted)}
    return {"keypad": False, "symbol_keys": []}
