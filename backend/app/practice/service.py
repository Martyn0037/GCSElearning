# backend/app/practice/service.py
"""Practice: serve the next question, reveal hints, mark answers, flag questions.

Concurrency and retries:
- "Next question" returns the open (unanswered) item for the topic if there is
  one, so a double tap or refresh doesn't create a second item.
- Answering locks the item row; the same ``Idempotency-Key`` replays the stored
  result, so a retry never double-counts progress.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AiUnavailableError
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.jobs.queue import enqueue
from app.models.curriculum import LearningObjective, Subtopic, Topic
from app.models.enrolment import StudentSubject, StudentTopicSetting
from app.models.question import (
    ExplanationStatus,
    Hint,
    Mistake,
    ObjectiveProgress,
    PracticeItem,
    Question,
    QuestionFlag,
    QuestionStatus,
)
from app.models.user import User
from app.practice import mastery
from app.practice.ladder import LadderState, Outcome, advance
from app.practice.review import FixedIntervalScheduler, ReviewScheduler, ReviewState, london_today
from app.practice.schemas import AnswerResultOut, OptionOut, PracticeItemOut
from app.questions.bank import pick_question, request_generation
from app.questions.generator import ObjectiveNotAvailableError, QuestionGenerator
from app.questions.marking import MarkResult, mark

logger = logging.getLogger(__name__)

# How long a student waits for an on-the-spot question before we give up and
# let the worker finish it in the background.
SYNC_GENERATION_TIMEOUT_SECONDS = 25.0
MAX_HINT_LEVEL = 4
EXPLAIN_JOB = "explain_mistake"


class PracticeService:
    """Practice use cases for one request. Mutating methods commit."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        now: datetime,
        generator: QuestionGenerator | None,
        scheduler: ReviewScheduler | None = None,
    ) -> None:
        """Create the service.

        Args:
            session: Request session.
            settings: App settings.
            now: Request time.
            generator: Used only when the bank is empty; ``None`` disables it.
            scheduler: When mistakes come back (default 1/3/7/14 days, ADR-006).
        """
        self._session = session
        self._settings = settings
        self._now = now
        self._generator = generator
        self._scheduler = scheduler or FixedIntervalScheduler()

    # ------------------------------------------------------------------ serve

    async def next_item(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID, topic_id: uuid.UUID
    ) -> PracticeItemOut:
        """Return the open item for this topic, or serve a new question.

        Raises:
            NotFoundError: Unknown or someone else's enrolment/topic.
            ConflictError: ``TOPIC_LOCKED`` (not covered at school yet) or
                ``QUESTIONS_PREPARING`` (no question available yet).
        """
        # Lock the subject row so simultaneous "next" requests serialise and
        # the second one finds the item the first created.
        enrolment = await self._enrolment(student_id, enrolment_id, lock=True)
        await self._require_unlocked_topic(enrolment, topic_id)

        open_item = await self._session.scalar(
            select(PracticeItem)
            .join(Question, Question.id == PracticeItem.question_id)
            .join(LearningObjective, LearningObjective.id == Question.objective_id)
            .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
            .where(
                PracticeItem.user_id == student_id,
                PracticeItem.enrolment_id == enrolment.id,
                PracticeItem.answered_at.is_(None),
                PracticeItem.mistake_id.is_(None),  # reviews resume separately
                Subtopic.topic_id == topic_id,
                Question.status == QuestionStatus.ACTIVE,
            )
            .order_by(PracticeItem.served_at.desc())
            .limit(1)
        )
        if open_item is not None:
            return await self._item_out(open_item)

        candidates = await self._objectives_by_priority(enrolment, topic_id)
        if not candidates:
            raise ConflictError("This topic has no skills on your tier.", code="TOPIC_EMPTY")
        for objective_id, level in candidates:
            question = await pick_question(
                self._session, student_id, objective_id, enrolment.tier, level
            )
            if question is None and objective_id == candidates[0][0]:
                question = await self._generate_now(objective_id, enrolment, level)
            if question is not None:
                return await self._serve(student_id, enrolment.id, question, level)

        for objective_id, level in candidates:
            await request_generation(self._session, objective_id, enrolment.tier, level, self._now)
        await self._session.commit()
        raise ConflictError(
            "We're preparing questions for this topic. Try again in a minute.",
            code="QUESTIONS_PREPARING",
        )

    async def _objectives_by_priority(
        self, enrolment: StudentSubject, topic_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, int]]:
        """Objectives in the topic on the student's tier, best to practise first.

        Order: lowest level, then least practised, then spec order.
        """
        rows = (
            await self._session.execute(
                select(LearningObjective, ObjectiveProgress)
                .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
                .outerjoin(
                    ObjectiveProgress,
                    and_(
                        ObjectiveProgress.objective_id == LearningObjective.id,
                        ObjectiveProgress.user_id == enrolment.student_id,
                    ),
                )
                .where(Subtopic.topic_id == topic_id, LearningObjective.retired_at.is_(None))
                .order_by(Subtopic.position, LearningObjective.position)
            )
        ).all()
        ranked = [
            (
                progress.level if progress else 1,
                progress.attempts if progress else 0,
                index,
                objective.id,
            )
            for index, (objective, progress) in enumerate(rows)
            if objective.text_for(enrolment.tier) is not None
        ]
        ranked.sort()
        return [(objective_id, level) for level, _, _, objective_id in ranked]

    async def _generate_now(
        self, objective_id: uuid.UUID, enrolment: StudentSubject, level: int
    ) -> Question | None:
        if self._generator is None:
            return None
        try:
            async with asyncio.timeout(SYNC_GENERATION_TIMEOUT_SECONDS):
                return await self._generator.generate(objective_id, enrolment.tier, level)
        except (AiUnavailableError, ObjectiveNotAvailableError, TimeoutError) as exc:
            logger.info("sync_generation_unavailable", extra={"error_type": type(exc).__name__})
            return None

    async def _serve(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID, question: Question, level: int
    ) -> PracticeItemOut:
        item = PracticeItem(
            id=uuid.uuid4(),
            user_id=student_id,
            enrolment_id=enrolment_id,
            question_id=question.id,
            difficulty=level,
            served_at=self._now,
            hints_revealed=0,
        )
        self._session.add(item)
        # Keep the bank ahead of the student for this objective.
        await request_generation(
            self._session, question.objective_id, question.tier, level, self._now
        )
        await request_generation(
            self._session, question.objective_id, question.tier, min(level + 1, 5), self._now
        )
        await self._session.commit()
        return await self._item_out(item, question)

    # ------------------------------------------------------------------ hints

    async def reveal_hint(self, student_id: uuid.UUID, item_id: uuid.UUID) -> PracticeItemOut:
        """Reveal the next hint (up to the full solution).

        Raises:
            NotFoundError: Unknown or someone else's item.
            ConflictError: Already answered, or every hint is shown.
        """
        item = await self._item(student_id, item_id, lock=True)
        if item.answered_at is not None:
            raise ConflictError("This question has already been answered.", code="ALREADY_ANSWERED")
        if item.hints_revealed >= MAX_HINT_LEVEL:
            raise ConflictError("All hints are already showing.", code="NO_MORE_HINTS")
        item.hints_revealed += 1
        await self._session.commit()
        return await self._item_out(item)

    # ------------------------------------------------------------------ answer

    async def submit(
        self, student_id: uuid.UUID, item_id: uuid.UUID, answer: str, idempotency_key: str
    ) -> AnswerResultOut:
        """Mark an answer, update mastery, ladder and mistakes (exactly once).

        - Practice answers move the difficulty ladder; review answers don't
          (they reschedule the mistake instead).
        - A wrong or full-solution answer opens (or re-opens) a mistake,
          scheduled for review and queued for an explanation.

        Raises:
            NotFoundError: Unknown or someone else's item.
            ConflictError: ``ALREADY_ANSWERED`` with a different idempotency key.
        """
        item = await self._item(student_id, item_id, lock=True)
        if item.answered_at is not None:
            if item.idempotency_key == idempotency_key and item.response:
                return AnswerResultOut.model_validate(item.response["result"])
            raise ConflictError("This question has already been answered.", code="ALREADY_ANSWERED")

        question = await self._session.get(Question, item.question_id)
        assert question is not None  # noqa: S101 - FK guarantees it
        result = mark(question.question_type, question.answer, question.options, answer)
        assisted = item.hints_revealed >= MAX_HINT_LEVEL
        outcome = (
            Outcome.ASSISTED
            if assisted
            else Outcome.CORRECT
            if result.correct
            else Outcome.INCORRECT
        )
        is_review = item.mistake_id is not None

        progress = await self._progress(student_id, question.objective_id)
        before = progress.level
        if not is_review:
            new_state = advance(
                LadderState(progress.level, tuple(Outcome(o) for o in progress.recent)), outcome
            )
            progress.level = new_state.level
            progress.recent = [o.value for o in new_state.recent]
        progress.mastery = mastery.update(
            progress.mastery, outcome, question.difficulty, question.question_type
        )
        progress.attempts += 1
        progress.correct += 1 if outcome is Outcome.CORRECT else 0
        progress.updated_at = self._now

        mistake_id: uuid.UUID | None = None
        resolved = False
        if is_review:
            resolved = await self._review_answered(item, outcome is Outcome.CORRECT, answer, result)
            mistake_id = item.mistake_id
        elif outcome is not Outcome.CORRECT:
            mistake_id = await self._record_mistake(
                item, question, answer, result.correct_answer_display, assisted
            )

        out = AnswerResultOut(
            item_id=item.id,
            correct=result.correct,
            assisted=assisted,
            correct_answer=result.correct_answer_display,
            worked_solution=question.worked_solution,
            level_before=before,
            level_after=progress.level,
            mistake_id=mistake_id,
            review=is_review,
            mistake_resolved=resolved,
        )
        item.answered_at = self._now
        item.idempotency_key = idempotency_key
        item.correct = result.correct
        item.assisted = assisted
        item.response = {"answer": answer, "result": out.model_dump(mode="json")}
        await self._session.commit()
        return out

    async def _progress(self, student_id: uuid.UUID, objective_id: uuid.UUID) -> ObjectiveProgress:
        progress = await self._session.get(
            ObjectiveProgress, (student_id, objective_id), with_for_update=True
        )
        if progress is None:
            progress = ObjectiveProgress(
                user_id=student_id,
                objective_id=objective_id,
                level=1,
                recent=[],
                attempts=0,
                correct=0,
                mastery=mastery.P_INIT,
            )
            self._session.add(progress)
        return progress

    async def _record_mistake(
        self,
        item: PracticeItem,
        question: Question,
        answer: str,
        correct_answer: str,
        assisted: bool,
    ) -> uuid.UUID:
        """Open a mistake, or re-open the existing one for this question."""
        schedule = self._scheduler.start(london_today(self._now))
        existing = await self._session.scalar(
            select(Mistake)
            .where(
                Mistake.user_id == item.user_id,
                Mistake.question_id == question.id,
                Mistake.resolved_at.is_(None),
            )
            .with_for_update()
        )
        mistake = existing or Mistake(
            id=uuid.uuid4(),
            user_id=item.user_id,
            enrolment_id=item.enrolment_id,
            question_id=question.id,
            objective_id=question.objective_id,
        )
        mistake.source_item_id = item.id
        mistake.student_answer = answer[:200]
        mistake.correct_answer = correct_answer[:300]
        mistake.assisted = assisted
        mistake.review_stage = schedule.stage
        mistake.correct_streak = schedule.correct_streak
        mistake.next_review_on = schedule.next_review_on
        mistake.explanation = None
        mistake.misconception = None
        mistake.explanation_status = (
            ExplanationStatus.PENDING
            if self._settings.anthropic_api_key
            else ExplanationStatus.UNAVAILABLE
        )
        if existing is None:
            self._session.add(mistake)
        await self._session.flush()
        if mistake.explanation_status is ExplanationStatus.PENDING:
            await enqueue(
                self._session,
                EXPLAIN_JOB,
                {"mistake_id": str(mistake.id)},
                self._now,
                dedupe_key=f"explain:{mistake.id}",
            )
        return mistake.id

    async def _review_answered(
        self, item: PracticeItem, correct: bool, answer: str, result: MarkResult
    ) -> bool:
        """Reschedule (or resolve) the mistake this review item was for."""
        mistake = await self._session.get(Mistake, item.mistake_id, with_for_update=True)
        if mistake is None or mistake.resolved_at is not None:
            return False
        state = self._scheduler.after_review(
            ReviewState(mistake.review_stage, mistake.correct_streak, mistake.next_review_on),
            correct,
            london_today(self._now),
        )
        mistake.review_stage = state.stage
        mistake.correct_streak = state.correct_streak
        mistake.next_review_on = state.next_review_on
        mistake.last_reviewed_at = self._now
        if not correct:
            mistake.student_answer = answer[:200]
            mistake.correct_answer = result.correct_answer_display[:300]
        if state.resolved:
            mistake.resolved_at = self._now
        return state.resolved

    # ------------------------------------------------------------------ similar & review

    async def similar(self, student_id: uuid.UUID, item_id: uuid.UUID) -> PracticeItemOut:
        """Serve another question on the same skill (after a wrong answer).

        Raises:
            NotFoundError: Unknown or someone else's item.
            ConflictError: ``QUESTIONS_PREPARING`` if none is available yet.
        """
        source = await self._item(student_id, item_id, lock=False)
        enrolment = await self._enrolment(student_id, source.enrolment_id, lock=True)
        question = await self._session.get(Question, source.question_id)
        assert question is not None  # noqa: S101 - FK guarantees it
        progress = await self._session.get(ObjectiveProgress, (student_id, question.objective_id))
        level = progress.level if progress else 1
        replacement = await pick_question(
            self._session,
            student_id,
            question.objective_id,
            enrolment.tier,
            level,
            exclude=question.id,
        )
        if replacement is None:
            replacement = await self._generate_now(question.objective_id, enrolment, level)
        if replacement is None:
            await request_generation(
                self._session, question.objective_id, enrolment.tier, level, self._now
            )
            await self._session.commit()
            raise ConflictError(
                "We're preparing more questions on this skill. Try again in a minute.",
                code="QUESTIONS_PREPARING",
            )
        return await self._serve(student_id, enrolment.id, replacement, level)

    async def next_review(self, student_id: uuid.UUID) -> PracticeItemOut:
        """Serve the next due mistake again (resuming an open review first).

        Raises:
            ConflictError: ``NO_REVIEWS_DUE`` when nothing is due today.
        """
        await self._session.execute(select(User.id).where(User.id == student_id).with_for_update())
        open_review = await self._session.scalar(
            select(PracticeItem)
            .where(
                PracticeItem.user_id == student_id,
                PracticeItem.mistake_id.is_not(None),
                PracticeItem.answered_at.is_(None),
            )
            .limit(1)
        )
        if open_review is not None:
            return await self._item_out(open_review)
        due = await self._session.scalar(
            select(Mistake)
            .join(Question, Question.id == Mistake.question_id)
            .where(
                Mistake.user_id == student_id,
                Mistake.resolved_at.is_(None),
                Mistake.next_review_on <= london_today(self._now),
                Question.status == QuestionStatus.ACTIVE,
            )
            .order_by(Mistake.next_review_on, Mistake.created_at)
            .limit(1)
        )
        if due is None:
            raise ConflictError("Nothing to review today. Nice work!", code="NO_REVIEWS_DUE")
        question = await self._session.get(Question, due.question_id)
        assert question is not None  # noqa: S101 - FK guarantees it
        item = PracticeItem(
            id=uuid.uuid4(),
            user_id=student_id,
            enrolment_id=due.enrolment_id,
            question_id=question.id,
            difficulty=question.difficulty,
            served_at=self._now,
            hints_revealed=0,
            mistake_id=due.id,
        )
        self._session.add(item)
        await self._session.commit()
        return await self._item_out(item, question)

    # ------------------------------------------------------------------ flag

    async def flag(self, student_id: uuid.UUID, item_id: uuid.UUID, reason: str | None) -> None:
        """Report a question as wrong: it's hidden from the student until reviewed. Idempotent."""
        item = await self._item(student_id, item_id, lock=False)
        existing = await self._session.scalar(
            select(QuestionFlag.id).where(
                QuestionFlag.question_id == item.question_id,
                QuestionFlag.user_id == student_id,
                QuestionFlag.resolved_at.is_(None),
            )
        )
        if existing is None:
            self._session.add(
                QuestionFlag(
                    question_id=item.question_id,
                    user_id=student_id,
                    reason=reason,
                    created_at=self._now,
                )
            )
        question = await self._session.get(Question, item.question_id, with_for_update=True)
        if question is not None and question.status is QuestionStatus.ACTIVE:
            question.status = QuestionStatus.FLAGGED
        await self._session.commit()
        logger.info("question_flagged", extra={"question_id": str(item.question_id)})

    # ------------------------------------------------------------------ helpers

    async def _enrolment(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID, *, lock: bool = False
    ) -> StudentSubject:
        enrolment = await self._session.get(StudentSubject, enrolment_id, with_for_update=lock)
        if enrolment is None or enrolment.student_id != student_id:
            raise NotFoundError("Subject not found")
        if enrolment.specification_id is None:
            raise ConflictError("This subject is still being set up.", code="SUBJECT_NOT_READY")
        return enrolment

    async def _require_unlocked_topic(self, enrolment: StudentSubject, topic_id: uuid.UUID) -> None:
        topic = await self._session.get(Topic, topic_id)
        if (
            topic is None
            or topic.specification_id != enrolment.specification_id
            or topic.retired_at
        ):
            raise NotFoundError("Topic not found")
        taught = await self._session.scalar(
            select(StudentTopicSetting.taught_at_school).where(
                StudentTopicSetting.student_id == enrolment.student_id,
                StudentTopicSetting.topic_id == topic_id,
            )
        )
        if not taught:
            raise ConflictError(
                "This topic hasn't been covered at school yet.", code="TOPIC_LOCKED"
            )

    async def _item(self, student_id: uuid.UUID, item_id: uuid.UUID, *, lock: bool) -> PracticeItem:
        item = await self._session.get(PracticeItem, item_id, with_for_update=lock)
        if item is None or item.user_id != student_id:
            raise NotFoundError("Question not found")
        return item

    async def _item_out(
        self, item: PracticeItem, question: Question | None = None
    ) -> PracticeItemOut:
        question = question or await self._session.get(Question, item.question_id)
        assert question is not None  # noqa: S101 - FK guarantees it
        objective_ref = await self._session.scalar(
            select(LearningObjective.ref).where(LearningObjective.id == question.objective_id)
        )
        hints = (
            await self._session.scalars(
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
        )
