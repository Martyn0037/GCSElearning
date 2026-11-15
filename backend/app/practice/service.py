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
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AiUnavailableError
from app.core.config import Settings
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.gamification.challenges import ChallengeService
from app.gamification.rewards import Rewards
from app.gamification.schemas import RewardsOut
from app.gamification.xp import level_for, xp_for_answer, xp_for_marks
from app.jobs.queue import enqueue
from app.models.curriculum import LearningObjective, Subtopic, Tier
from app.models.enrolment import StudentSubject
from app.models.gamification import Challenge, ChallengeKind, XpSource
from app.models.question import (
    ExplanationStatus,
    Mistake,
    ObjectiveProgress,
    PracticeItem,
    Question,
    QuestionFlag,
    QuestionStatus,
    QuestionType,
)
from app.models.user import User
from app.practice import mastery
from app.practice.extended import ExtendedMark, ExtendedMarker, scheme
from app.practice.items import (
    MAX_HINT_LEVEL,
    item_out,
    load_enrolment,
    require_unlocked_topic,
)
from app.practice.ladder import LadderState, Outcome, advance
from app.practice.review import FixedIntervalScheduler, ReviewScheduler, ReviewState, london_today
from app.practice.schemas import (
    AnswerResultOut,
    ExtendedMarkingOut,
    LevelOut,
    MarkPointOut,
    PracticeItemOut,
)
from app.questions.bank import pick_question, request_generation
from app.questions.generator import ObjectiveNotAvailableError, QuestionGenerator
from app.questions.marking import MAX_ANSWER_LENGTH, mark

logger = logging.getLogger(__name__)

# How long a student waits for an on-the-spot question before we give up and
# let the worker finish it in the background.
SYNC_GENERATION_TIMEOUT_SECONDS = 25.0
# When the best skill has no question ready, look this far down the list for a
# skill at the same level that does, rather than make the student wait while
# one is written.
READY_LOOKAHEAD = 5
# Skills to start writing questions for as soon as one is served, so the next
# "Next question" finds one waiting.
PREFETCH_SKILLS = 2
EXPLAIN_JOB = "explain_mistake"


# A marking attempt older than this is assumed lost (e.g. the server restarted).
MARKING_STALE_AFTER = timedelta(minutes=3)


@dataclass(frozen=True, slots=True)
class Marked:
    """A marked answer, however it was marked."""

    correct: bool
    display: str  # the correct answer (or model answer) to show
    xp: int
    extended: ExtendedMark | None = None
    unmarked: bool = False  # Claude couldn't mark this extended answer


def marking_out(question: Question, extended: ExtendedMark | None) -> ExtendedMarkingOut:
    """The marking breakdown shown under an extended answer."""
    points, levels = scheme(question)
    awarded = set(extended.awarded_points) if extended else set()
    return ExtendedMarkingOut(
        marks=extended.marks if extended else None,
        marks_available=question.marks,
        level=extended.level if extended else None,
        levels=[LevelOut(**lv) for lv in levels],
        points=[
            MarkPointOut(text=p["text"], marks=p["marks"], ao=p["ao"], awarded=i in awarded)
            for i, p in enumerate(points, 1)
        ],
        strengths=extended.strengths if extended else None,
        improvements=extended.improvements if extended else None,
    )


class PracticeService:
    """Practice use cases for one request. Mutating methods commit."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        now: datetime,
        generator: QuestionGenerator | None,
        scheduler: ReviewScheduler | None = None,
        marker: ExtendedMarker | None = None,
    ) -> None:
        """Create the service.

        Args:
            session: Request session.
            settings: App settings.
            now: Request time.
            generator: Used only when the bank is empty; ``None`` disables it.
            scheduler: When mistakes come back (default 1/3/7/14 days, ADR-006).
            marker: Marks extended answers; ``None`` leaves them unmarked.
        """
        self._session = session
        self._settings = settings
        self._now = now
        self._generator = generator
        self._scheduler = scheduler or FixedIntervalScheduler()
        self._marker = marker

    # ------------------------------------------------------------------ serve

    async def next_item(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID, topic_id: uuid.UUID
    ) -> PracticeItemOut:
        """Return the open item for this topic, or serve a new question.

        Raises:
            NotFoundError: Unknown or someone else's enrolment/topic.
            ConflictError: ``QUESTIONS_PREPARING`` (no question available yet).
        """
        # Lock the subject row so simultaneous "next" requests serialise and
        # the second one finds the item the first created.
        enrolment = await load_enrolment(self._session, student_id, enrolment_id, lock=True)
        await require_unlocked_topic(self._session, enrolment, topic_id)

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
                PracticeItem.challenge_id.is_(None),  # so do challenges
                Subtopic.topic_id == topic_id,
                Question.status == QuestionStatus.ACTIVE,
            )
            .order_by(PracticeItem.served_at.desc())
            .limit(1)
        )
        if open_item is not None:
            return await item_out(self._session, open_item)

        candidates = await self._objectives_by_priority(enrolment, topic_id)
        if not candidates:
            raise ConflictError("This topic has no skills on your tier.", code="TOPIC_EMPTY")
        served = await self._ready_or_generated(student_id, enrolment, candidates)
        if served is not None:
            question, level = served
            # The next few in line are what the next request will want.
            upcoming = [c for c in candidates if c[0] != question.objective_id][:PREFETCH_SKILLS]
            return await self._serve(
                student_id, enrolment.id, question, level, upcoming=upcoming, tier=enrolment.tier
            )

        # Nothing ready anywhere: get the first few written first. Not every
        # skill in the topic, which could be a hundred jobs for a big topic.
        for objective_id, level in candidates[: 1 + PREFETCH_SKILLS]:
            await request_generation(
                self._session, objective_id, enrolment.tier, level, self._now, urgent=True
            )
        await self._session.commit()
        raise ConflictError(
            "We're preparing questions for this topic. Try again in a minute.",
            code="QUESTIONS_PREPARING",
        )

    async def _ready_or_generated(
        self,
        student_id: uuid.UUID,
        enrolment: StudentSubject,
        candidates: list[tuple[uuid.UUID, int]],
    ) -> tuple[Question, int] | None:
        """A question for the best skill that can be served now.

        In order: a banked question for the top skill; a banked question for one
        of the next few skills at the same level (the top skill is then queued
        urgently, so it's ready soon); a question written now for the top skill;
        finally a banked question for any skill.
        """
        top_id, top_level = candidates[0]
        question = await pick_question(self._session, student_id, top_id, enrolment.tier, top_level)
        if question is not None:
            return question, top_level
        for objective_id, level in candidates[1 : 1 + READY_LOOKAHEAD]:
            if level != top_level:
                break
            question = await pick_question(
                self._session, student_id, objective_id, enrolment.tier, level
            )
            if question is not None:
                await request_generation(
                    self._session, top_id, enrolment.tier, top_level, self._now, urgent=True
                )
                return question, level
        question = await self._generate_now(top_id, enrolment, top_level)
        if question is not None:
            return question, top_level
        for objective_id, level in candidates[1 + READY_LOOKAHEAD :]:
            question = await pick_question(
                self._session, student_id, objective_id, enrolment.tier, level
            )
            if question is not None:
                return question, level
        return None

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
        self,
        student_id: uuid.UUID,
        enrolment_id: uuid.UUID,
        question: Question,
        level: int,
        *,
        upcoming: list[tuple[uuid.UUID, int]] | None = None,
        tier: Tier | None = None,
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
        # Get the skills likely to come next written first (they jump the queue).
        for objective_id, upcoming_level in upcoming or []:
            await request_generation(
                self._session, objective_id, tier, upcoming_level, self._now, urgent=True
            )
        # Keep the bank ahead of the student for this objective ("Try a similar one").
        await request_generation(
            self._session, question.objective_id, question.tier, level, self._now
        )
        await request_generation(
            self._session, question.objective_id, question.tier, min(level + 1, 5), self._now
        )
        await self._session.commit()
        return await item_out(self._session, item, question)

    # ------------------------------------------------------------------ hints

    async def reveal_hint(self, student_id: uuid.UUID, item_id: uuid.UUID) -> PracticeItemOut:
        """Reveal the next hint (up to the full solution).

        Raises:
            NotFoundError: Unknown or someone else's item.
            ConflictError: Already answered, every hint is shown, or
                ``HINTS_OFF`` in a boss battle (exam conditions).
        """
        item = await self._item(student_id, item_id, lock=True)
        if item.answered_at is not None:
            raise ConflictError("This question has already been answered.", code="ALREADY_ANSWERED")
        if item.challenge_id is not None:
            challenge = await self._session.get(Challenge, item.challenge_id)
            if challenge is not None and challenge.kind is ChallengeKind.BOSS:
                raise ConflictError("No hints in a boss battle.", code="HINTS_OFF")
        if item.hints_revealed >= MAX_HINT_LEVEL:
            raise ConflictError("All hints are already showing.", code="NO_MORE_HINTS")
        item.hints_revealed += 1
        await self._session.commit()
        return await item_out(self._session, item)

    # ------------------------------------------------------------------ answer

    async def submit(
        self, student_id: uuid.UUID, item_id: uuid.UUID, answer: str, idempotency_key: str
    ) -> AnswerResultOut:
        """Mark an answer, update mastery, ladder and mistakes (exactly once).

        - Practice answers move the difficulty ladder; review answers don't
          (they reschedule the mistake instead).
        - A wrong or full-solution answer opens (or re-opens) a mistake,
          scheduled for review and queued for an explanation.
        - XP, the streak and badges are updated (ADR-016); answering the last
          question of a challenge completes it and adds its bonus.
        - Boss battle answers don't move the ladder (they're set above it).
        - Extended answers are marked by Claude outside any transaction
          (ADR-018); if Claude can't mark them, the answer is kept, the mark
          scheme is shown and nothing counts against the student.

        Raises:
            NotFoundError: Unknown or someone else's item.
            ConflictError: ``ALREADY_ANSWERED`` with a different idempotency key;
                ``CHALLENGE_FINISHED`` or ``TIME_UP`` for a closed challenge;
                ``MARKING_IN_PROGRESS`` while the same answer is being marked.
            InvalidRequestError: ``ANSWER_TOO_LONG`` for a short answer over 200
                characters.
        """
        item = await self._item(student_id, item_id, lock=True)
        replay = self._replay(item, idempotency_key)
        if replay is not None:
            return replay
        question = await self._session.get(Question, item.question_id)
        assert question is not None  # noqa: S101 - FK guarantees it
        challenges = ChallengeService(self._session, self._now)
        challenge = await self._open_challenge(item, challenges)

        if question.question_type is QuestionType.EXTENDED:
            return await self._submit_extended(
                student_id, item, question, answer, idempotency_key, challenges
            )
        if len(answer) > MAX_ANSWER_LENGTH:
            raise InvalidRequestError(
                f"Answers are at most {MAX_ANSWER_LENGTH} characters.", code="ANSWER_TOO_LONG"
            )
        result = mark(question.question_type, question.answer, question.options, answer)
        marked = Marked(
            correct=result.correct,
            display=result.correct_answer_display,
            xp=xp_for_answer(question.difficulty, result.correct, item.hints_revealed),
        )
        return await self._finish(
            item, question, answer, idempotency_key, marked, challenges, challenge
        )

    def _replay(self, item: PracticeItem, idempotency_key: str) -> AnswerResultOut | None:
        """The stored result for a repeated request, or a conflict for a different one."""
        if item.answered_at is not None:
            if item.idempotency_key == idempotency_key and item.response:
                return AnswerResultOut.model_validate(item.response["result"])
            raise ConflictError("This question has already been answered.", code="ALREADY_ANSWERED")
        if item.marking_started_at is not None and (
            self._now - item.marking_started_at < MARKING_STALE_AFTER
        ):
            raise ConflictError(
                "Your answer is still being marked. Try again in a moment.",
                code="MARKING_IN_PROGRESS",
            )
        return None

    async def _open_challenge(
        self, item: PracticeItem, challenges: ChallengeService
    ) -> Challenge | None:
        if item.challenge_id is None:
            return None
        challenge = await self._session.get(Challenge, item.challenge_id, with_for_update=True)
        assert challenge is not None  # noqa: S101 - FK guarantees it
        await challenges.ensure_answerable(challenge)
        return challenge

    async def _submit_extended(
        self,
        student_id: uuid.UUID,
        item: PracticeItem,
        question: Question,
        answer: str,
        idempotency_key: str,
        challenges: ChallengeService,
    ) -> AnswerResultOut:
        """Mark a written answer in three steps so no lock is held while Claude marks it."""
        # 1. Record that marking has started, and release the locks.
        item.marking_started_at = self._now
        item.idempotency_key = idempotency_key
        item.response = {"answer": answer}
        await self._session.commit()

        # 2. Ask Claude, outside any transaction.
        extended: ExtendedMark | None = None
        if self._marker is not None:
            try:
                extended = await self._marker.mark(question, answer)
            except AiUnavailableError as exc:
                logger.info("extended_marking_unavailable", extra={"reason": exc.reason})

        # 3. Apply the result (unless another request finished it meanwhile).
        item = await self._item(student_id, item.id, lock=True)
        await self._session.refresh(item)
        if item.answered_at is not None:
            return AnswerResultOut.model_validate((item.response or {})["result"])
        challenge = await self._open_challenge(item, challenges)
        model_answer = str(question.answer.get("model_answer") or question.worked_solution)
        marked = Marked(
            correct=extended.secure if extended else False,
            display=model_answer,
            xp=xp_for_marks(question.difficulty, extended.fraction, item.hints_revealed)
            if extended
            else 0,
            extended=extended,
            unmarked=extended is None,
        )
        return await self._finish(
            item, question, answer, idempotency_key, marked, challenges, challenge
        )

    async def _finish(
        self,
        item: PracticeItem,
        question: Question,
        answer: str,
        idempotency_key: str,
        marked: Marked,
        challenges: ChallengeService,
        challenge: Challenge | None,
    ) -> AnswerResultOut:
        """Record a marked answer: mastery, ladder, mistakes, challenge, rewards."""
        student_id = item.user_id
        assisted = item.hints_revealed >= MAX_HINT_LEVEL
        outcome = (
            Outcome.ASSISTED
            if assisted
            else Outcome.CORRECT
            if marked.correct
            else Outcome.INCORRECT
        )
        is_review = item.mistake_id is not None
        is_boss = challenge is not None and challenge.kind is ChallengeKind.BOSS

        progress = await self._progress(student_id, question.objective_id)
        before = progress.level
        mistake_id: uuid.UUID | None = None
        resolved = False
        if not marked.unmarked:  # an answer Claude couldn't mark doesn't count either way
            if not is_review and not is_boss:
                new_state = advance(
                    LadderState(progress.level, tuple(Outcome(o) for o in progress.recent)),
                    outcome,
                )
                progress.level = new_state.level
                progress.recent = [o.value for o in new_state.recent]
            progress.mastery = mastery.update(
                progress.mastery, outcome, question.difficulty, question.question_type
            )
            progress.attempts += 1
            progress.correct += 1 if outcome is Outcome.CORRECT else 0
            progress.updated_at = self._now
            if is_review:
                resolved = await self._review_answered(
                    item, outcome is Outcome.CORRECT, answer, marked.display
                )
                mistake_id = item.mistake_id
            elif outcome is not Outcome.CORRECT:
                mistake_id = await self._record_mistake(
                    item, question, answer, marked.display, assisted
                )

        item.answered_at = self._now
        item.correct = marked.correct
        item.assisted = assisted
        item.marking_started_at = None
        await self._session.flush()
        progress_out, bonus = await challenges.after_answer(challenge) if challenge else (None, 0)
        rewards = await self._rewards(item, question, marked.xp, challenges, bonus)

        out = AnswerResultOut(
            item_id=item.id,
            correct=marked.correct,
            assisted=assisted,
            correct_answer=marked.display,
            worked_solution=question.worked_solution,
            level_before=before,
            level_after=progress.level,
            mistake_id=mistake_id,
            review=is_review,
            mistake_resolved=resolved,
            rewards=rewards,
            challenge=progress_out,
            marked=not marked.unmarked,
            marking=marking_out(question, marked.extended)
            if question.question_type is QuestionType.EXTENDED
            else None,
        )
        item.idempotency_key = idempotency_key
        item.response = {"answer": answer, "result": out.model_dump(mode="json")}
        await self._session.commit()
        return out

    async def _rewards(
        self,
        item: PracticeItem,
        question: Question,
        xp: int,
        challenges: ChallengeService,
        bonus: int,
    ) -> RewardsOut:
        """XP for this answer (plus any challenge bonus), the streak, and new badges."""
        rewards = Rewards(self._session, self._now)
        total_after = await rewards.total_xp(item.user_id)  # includes any bonus just added
        gained = await rewards.award(item.user_id, XpSource.ANSWER, item.id, xp)
        total_after += gained
        level_before = level_for(total_after - gained - bonus).level
        streak = await rewards.record_activity(item.user_id)
        enrolment = await self._session.get(StudentSubject, item.enrolment_id)
        topic_id = await self._session.scalar(
            select(Subtopic.topic_id)
            .join(LearningObjective, LearningObjective.subtopic_id == Subtopic.id)
            .where(LearningObjective.id == question.objective_id)
        )
        exam_ready = (
            enrolment is not None
            and topic_id is not None
            and await challenges.exam_ready_reached(enrolment, topic_id)
        )
        badges = await rewards.grant_badges(item.user_id, exam_ready_topic=exam_ready)
        level = level_for(total_after)
        return RewardsOut(
            xp_gained=gained,
            bonus_xp=bonus,
            total_xp=total_after,
            level=level.level,
            level_up=level.level > level_before,
            xp_into_level=level.xp_into_level,
            xp_for_level=level.xp_for_level,
            streak_days=streak.state.current,
            streak_extended=streak.extended,
            used_freeze=streak.used_freeze,
            new_badges=badges,
        )

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
        self, item: PracticeItem, correct: bool, answer: str, correct_answer: str
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
            mistake.correct_answer = correct_answer[:300]
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
        enrolment = await load_enrolment(self._session, student_id, source.enrolment_id, lock=True)
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
                PracticeItem.challenge_id.is_(None),
                PracticeItem.answered_at.is_(None),
            )
            .limit(1)
        )
        if open_review is not None:
            return await item_out(self._session, open_review)
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
        return await item_out(self._session, item, question)

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

    async def _item(self, student_id: uuid.UUID, item_id: uuid.UUID, *, lock: bool) -> PracticeItem:
        item = await self._session.get(PracticeItem, item_id, with_for_update=lock)
        if item is None or item.user_id != student_id:
            raise NotFoundError("Question not found")
        return item
