# backend/app/practice/items.py
"""Shared practice helpers: the question as the student sees it, and access checks.

Used by topic practice, reviews and challenges alike.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.curriculum import LearningObjective, Specification, Subject, Topic
from app.models.enrolment import StudentSubject
from app.models.question import Hint, PracticeItem, Question
from app.practice.schemas import OptionOut, PracticeItemOut
from app.questions.keyboards import keys_for

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
    row = (
        await session.execute(
            select(LearningObjective.ref, Subject.slug)
            .join(Specification, Specification.id == LearningObjective.specification_id)
            .join(Subject, Subject.id == Specification.subject_id)
            .where(LearningObjective.id == question.objective_id)
        )
    ).first()
    objective_ref, subject_slug = row if row else ("", None)
    keys = keys_for(question, subject_slug)
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
        keypad=keys.keypad,
        number_keys=keys.number_keys,
        symbol_keys=keys.symbol_keys,
    )
