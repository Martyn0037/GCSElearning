# backend/app/gamification/challenges.py
"""Daily challenges and boss battles.

A challenge's questions are ordinary practice items (with ``challenge_id`` and
``position``), so marking, mistakes, reviews, idempotent answers and XP all
work exactly as in topic practice. This service chooses the questions, serves
them in order, and scores the challenge when the last one is answered, when
the student ends a boss battle, or when its time runs out.

Concurrency: starting a challenge locks the student's row (daily) or subject
row (boss), so a double tap returns the same challenge; partial unique indexes
back this up. Completion locks the challenge row and is a no-op if repeated.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.gamification import selection
from app.gamification.grading import estimate
from app.gamification.rewards import Rewards
from app.gamification.rings import Ring
from app.gamification.schemas import (
    ChallengeItemResultOut,
    ChallengeOut,
    ChallengeProgressOut,
    GradeEstimateOut,
)
from app.gamification.standings import boss_bests, on_tier, topic_standings
from app.gamification.xp import DAILY_CHALLENGE_BONUS, boss_bonus
from app.models.curriculum import LearningObjective, Subtopic, Tier, Topic
from app.models.enrolment import StudentSubject, StudentTopicSetting
from app.models.gamification import (
    Challenge,
    ChallengeKind,
    ChallengeStatus,
    GradeBoundary,
    XpEvent,
    XpSource,
)
from app.models.question import Mistake, ObjectiveProgress, PracticeItem, Question, QuestionStatus
from app.models.user import User
from app.practice.items import item_out, load_enrolment, require_unlocked_topic
from app.practice.review import london_today
from app.practice.schemas import PracticeItemOut
from app.questions.bank import pick_question, request_generation
from app.questions.marking import mark

logger = logging.getLogger(__name__)


def marks_earned(item: PracticeItem, marks: int) -> int:
    """Marks an answer earned: Claude's mark for a written answer, else all or nothing.

    An answer given after the full solution earns nothing in a challenge.
    """
    if item.answered_at is None or item.assisted:
        return 0
    marking = ((item.response or {}).get("result") or {}).get("marking")
    if marking is not None:
        return int(marking.get("marks") or 0)
    return marks if item.correct else 0


class ChallengeService:
    """Challenge use cases for one request. Public methods commit."""

    def __init__(self, session: AsyncSession, now: datetime) -> None:
        """Create the service.

        Args:
            session: Request session.
            now: Request time.
        """
        self._session = session
        self._now = now
        self._rewards = Rewards(session, now)

    # ------------------------------------------------------------------ start

    async def start_daily(self, student_id: uuid.UUID) -> ChallengeOut:
        """Today's daily challenge, created on first request. Safe to repeat.

        Up to 5 questions: up to 2 mistakes due for review, then the weakest
        skills across every unlocked topic (at most 2 per topic).

        Raises:
            ConflictError: ``NOTHING_TO_PRACTISE`` with no unlocked topics, or
                ``QUESTIONS_PREPARING`` when no question is ready yet.
        """
        await self._session.execute(select(User.id).where(User.id == student_id).with_for_update())
        today = london_today(self._now)
        existing = await self._session.scalar(
            select(Challenge).where(
                Challenge.user_id == student_id,
                Challenge.kind == ChallengeKind.DAILY,
                Challenge.london_date == today,
            )
        )
        if existing is not None:
            return await self._out(existing)

        items: list[PracticeItem] = []
        for mistake, due_question in await self._due_reviews(student_id, today):
            items.append(
                self._item(student_id, mistake.enrolment_id, due_question, mistake_id=mistake.id)
            )

        candidates, tiers = await self._candidates(student_id)
        if not candidates and not items:
            raise ConflictError(
                "There's nothing to practise yet: a topic needs to be unlocked first.",
                code="NOTHING_TO_PRACTISE",
            )
        used: set[uuid.UUID] = set()
        for candidate in selection.rank_daily(candidates):
            if len(items) >= selection.DAILY_SIZE:
                break
            if candidate.objective_id in used:
                continue
            tier = tiers[candidate.enrolment_id]
            question = await pick_question(
                self._session, student_id, candidate.objective_id, tier, candidate.level
            )
            if question is None:
                await request_generation(
                    self._session, candidate.objective_id, tier, candidate.level, self._now
                )
                continue
            used.add(candidate.objective_id)
            items.append(self._item(student_id, candidate.enrolment_id, question))

        if not items:
            await self._session.commit()  # keep the generation requests
            raise ConflictError(
                "We're preparing today's challenge. Try again in a minute.",
                code="QUESTIONS_PREPARING",
            )
        challenge = Challenge(
            id=uuid.uuid4(),
            user_id=student_id,
            kind=ChallengeKind.DAILY,
            status=ChallengeStatus.ACTIVE,
            london_date=today,
            started_at=self._now,
        )
        return await self._create(challenge, items)

    async def start_boss(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID, topic_id: uuid.UUID
    ) -> ChallengeOut:
        """Start a timed boss battle on a topic, or return the one in progress.

        Questions sample the whole topic (up to 6 skills, spread through it),
        one level above the student's own and at least "apply". No hints.

        Raises:
            NotFoundError: Unknown or someone else's subject or topic.
            ConflictError: ``TOPIC_LOCKED``; ``BOSS_LOCKED`` until half the
                topic's skills are practised; ``QUESTIONS_PREPARING``.
        """
        enrolment = await load_enrolment(self._session, student_id, enrolment_id, lock=True)
        await require_unlocked_topic(self._session, enrolment, topic_id)
        standing = (await topic_standings(self._session, enrolment, [topic_id])).get(topic_id)
        if standing is None or not standing.boss_unlocked:
            needed = standing.skills_to_unlock_boss if standing else 0
            raise ConflictError(
                f"Practise {needed} more skill{'s' if needed != 1 else ''} in this topic "
                "to unlock its boss battle.",
                code="BOSS_LOCKED",
            )
        active = await self._session.scalar(
            select(Challenge)
            .where(
                Challenge.user_id == student_id,
                Challenge.kind == ChallengeKind.BOSS,
                Challenge.topic_id == topic_id,
                Challenge.status == ChallengeStatus.ACTIVE,
            )
            .with_for_update()
        )
        if active is not None:
            if not self._expired(active):
                return await self._out(active)
            await self._complete(active)

        objectives = await self._topic_objectives(enrolment, topic_id)
        levels = dict(objectives)
        items: list[PracticeItem] = []
        questions: list[Question] = []
        for objective_id in selection.spread([o for o, _ in objectives]):
            target = selection.boss_difficulty(levels[objective_id])
            question = None
            for difficulty in selection.difficulty_fallbacks(target):
                question = await pick_question(
                    self._session, student_id, objective_id, enrolment.tier, difficulty
                )
                if question is not None:
                    break
            if question is None:
                await request_generation(
                    self._session, objective_id, enrolment.tier, target, self._now
                )
                continue
            questions.append(question)
            items.append(self._item(student_id, enrolment.id, question))
        if len(items) < min(selection.BOSS_MIN_QUESTIONS, len(objectives)) or not items:
            await self._session.commit()  # keep the generation requests
            raise ConflictError(
                "We're preparing this boss battle. Try again in a few minutes.",
                code="QUESTIONS_PREPARING",
            )
        minutes = selection.boss_minutes(sum(q.marks for q in questions))
        challenge = Challenge(
            id=uuid.uuid4(),
            user_id=student_id,
            kind=ChallengeKind.BOSS,
            status=ChallengeStatus.ACTIVE,
            london_date=london_today(self._now),
            enrolment_id=enrolment.id,
            topic_id=topic_id,
            started_at=self._now,
            deadline_at=self._now + timedelta(minutes=minutes),
        )
        return await self._create(challenge, items)

    # ------------------------------------------------------------------ play

    async def get(self, student_id: uuid.UUID, challenge_id: uuid.UUID) -> ChallengeOut:
        """A challenge's state (a boss battle past its time is scored first)."""
        challenge = await self._own(student_id, challenge_id, lock=True)
        if challenge.status is ChallengeStatus.ACTIVE and self._expired(challenge):
            await self._complete(challenge)
            await self._session.commit()
        return await self._out(challenge)

    async def next_item(self, student_id: uuid.UUID, challenge_id: uuid.UUID) -> PracticeItemOut:
        """The next unanswered question, in order.

        Raises:
            NotFoundError: Unknown or someone else's challenge.
            ConflictError: ``TIME_UP`` or ``CHALLENGE_FINISHED``.
        """
        challenge = await self._own(student_id, challenge_id, lock=True)
        await self.ensure_answerable(challenge)
        item = await self._session.scalar(
            select(PracticeItem)
            .where(PracticeItem.challenge_id == challenge.id, PracticeItem.answered_at.is_(None))
            .order_by(PracticeItem.position)
            .limit(1)
        )
        if item is None:  # every question answered: finish it off
            await self._complete(challenge)
            await self._session.commit()
            raise ConflictError("This challenge is finished.", code="CHALLENGE_FINISHED")
        return await item_out(self._session, item)

    async def finish(self, student_id: uuid.UUID, challenge_id: uuid.UUID) -> ChallengeOut:
        """End a boss battle now; unanswered questions score nothing. Safe to repeat.

        Raises:
            ConflictError: ``NOT_A_BOSS_BATTLE`` for a daily challenge.
        """
        challenge = await self._own(student_id, challenge_id, lock=True)
        if challenge.kind is not ChallengeKind.BOSS:
            raise ConflictError("Only boss battles can be ended early.", code="NOT_A_BOSS_BATTLE")
        if challenge.status is ChallengeStatus.ACTIVE:
            await self._complete(challenge)
            await self._session.commit()
        return await self._out(challenge)

    # ------------------------------------------------------------------ used when answering

    async def ensure_answerable(self, challenge: Challenge) -> None:
        """Refuse answers to a finished challenge, scoring a timed-out one first.

        The caller holds the challenge row lock. On ``TIME_UP`` the scoring is
        committed before raising.

        Raises:
            ConflictError: ``CHALLENGE_FINISHED`` or ``TIME_UP``.
        """
        if challenge.status is ChallengeStatus.COMPLETED:
            raise ConflictError("This challenge is finished.", code="CHALLENGE_FINISHED")
        if self._expired(challenge):
            await self._complete(challenge)
            await self._session.commit()
            raise ConflictError("Time's up for this boss battle.", code="TIME_UP")

    async def after_answer(self, challenge: Challenge) -> tuple[ChallengeProgressOut, int]:
        """Progress after one more answer; completes the challenge on the last one.

        Returns:
            The progress, and the completion bonus XP awarded now (0 if none).
        """
        total, answered = await self._counts(challenge.id)
        bonus = 0
        if answered >= total:
            bonus = await self._complete(challenge, grant_badges=False)
        progress = ChallengeProgressOut(
            challenge_id=challenge.id,
            kind=challenge.kind,
            answered=answered,
            total=total,
            completed=challenge.status is ChallengeStatus.COMPLETED,
        )
        return progress, bonus

    async def exam_ready_reached(self, enrolment: StudentSubject, topic_id: uuid.UUID) -> bool:
        """Whether the topic is now "exam ready" (cheap check first: a 70%+ boss score)."""
        best = (await boss_bests(self._session, enrolment.student_id, [topic_id])).get(topic_id)
        if best is None or best < 70:
            return False
        standing = (await topic_standings(self._session, enrolment, [topic_id])).get(topic_id)
        return standing is not None and standing.ring is Ring.EXAM_READY

    # ------------------------------------------------------------------ internals

    def _expired(self, challenge: Challenge) -> bool:
        return challenge.deadline_at is not None and self._now > challenge.deadline_at + timedelta(
            seconds=selection.BOSS_GRACE_SECONDS
        )

    def _item(
        self,
        student_id: uuid.UUID,
        enrolment_id: uuid.UUID,
        question: Question,
        *,
        mistake_id: uuid.UUID | None = None,
    ) -> PracticeItem:
        return PracticeItem(
            id=uuid.uuid4(),
            user_id=student_id,
            enrolment_id=enrolment_id,
            question_id=question.id,
            difficulty=question.difficulty,
            served_at=self._now,
            hints_revealed=0,
            mistake_id=mistake_id,
        )

    async def _create(self, challenge: Challenge, items: list[PracticeItem]) -> ChallengeOut:
        self._session.add(challenge)
        await self._session.flush()
        for position, item in enumerate(items, start=1):
            item.challenge_id = challenge.id
            item.position = position
            self._session.add(item)
        await self._session.commit()
        logger.info(
            "challenge_started",
            extra={"challenge_kind": challenge.kind.value, "questions": len(items)},
        )
        return await self._out(challenge)

    async def _own(
        self, student_id: uuid.UUID, challenge_id: uuid.UUID, *, lock: bool
    ) -> Challenge:
        challenge = await self._session.get(Challenge, challenge_id, with_for_update=lock)
        if challenge is None or challenge.user_id != student_id:
            raise NotFoundError("Challenge not found")
        return challenge

    async def _counts(self, challenge_id: uuid.UUID) -> tuple[int, int]:
        total, answered = (
            await self._session.execute(
                select(func.count(), func.count(PracticeItem.answered_at)).where(
                    PracticeItem.challenge_id == challenge_id
                )
            )
        ).one()
        return total, answered

    async def _due_reviews(
        self, student_id: uuid.UUID, today: date
    ) -> list[tuple[Mistake, Question]]:
        rows = (
            await self._session.execute(
                select(Mistake, Question)
                .join(Question, Question.id == Mistake.question_id)
                .where(
                    Mistake.user_id == student_id,
                    Mistake.resolved_at.is_(None),
                    Mistake.next_review_on <= today,
                    Question.status == QuestionStatus.ACTIVE,
                )
                .order_by(Mistake.next_review_on, Mistake.created_at)
                .limit(selection.DAILY_MAX_REVIEWS)
            )
        ).all()
        return [(mistake, question) for mistake, question in rows]

    async def _candidates(
        self, student_id: uuid.UUID
    ) -> tuple[list[selection.Candidate], dict[uuid.UUID, Tier | None]]:
        """Every skill on the student's tier in topics covered at school, across subjects."""
        rows = (
            await self._session.execute(
                select(StudentSubject, Subtopic.topic_id, LearningObjective, ObjectiveProgress)
                .join(Topic, Topic.specification_id == StudentSubject.specification_id)
                .join(
                    StudentTopicSetting,
                    and_(
                        StudentTopicSetting.topic_id == Topic.id,
                        StudentTopicSetting.student_id == student_id,
                        StudentTopicSetting.taught_at_school.is_(True),
                    ),
                )
                .join(Subtopic, Subtopic.topic_id == Topic.id)
                .join(LearningObjective, LearningObjective.subtopic_id == Subtopic.id)
                .outerjoin(
                    ObjectiveProgress,
                    and_(
                        ObjectiveProgress.objective_id == LearningObjective.id,
                        ObjectiveProgress.user_id == student_id,
                    ),
                )
                .where(
                    StudentSubject.student_id == student_id,
                    Topic.retired_at.is_(None),
                    Subtopic.retired_at.is_(None),
                    LearningObjective.retired_at.is_(None),
                )
                .order_by(
                    StudentSubject.position,
                    Topic.position,
                    Subtopic.position,
                    LearningObjective.position,
                )
            )
        ).all()
        candidates: list[selection.Candidate] = []
        tiers: dict[uuid.UUID, Tier | None] = {}
        for order, (enrolment, topic_id, objective, progress) in enumerate(rows):
            if objective.text_for(enrolment.tier) is None:
                continue
            tiers[enrolment.id] = enrolment.tier
            candidates.append(
                selection.Candidate(
                    objective_id=objective.id,
                    enrolment_id=enrolment.id,
                    topic_id=topic_id,
                    level=progress.level if progress else 1,
                    mastery=progress.mastery if progress else 0.0,
                    attempts=progress.attempts if progress else 0,
                    order=order,
                )
            )
        return candidates, tiers

    async def _topic_objectives(
        self, enrolment: StudentSubject, topic_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, int]]:
        """The topic's skills on the student's tier, in spec order, with their level."""
        rows = (
            await self._session.execute(
                select(LearningObjective.id, ObjectiveProgress.level)
                .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
                .outerjoin(
                    ObjectiveProgress,
                    and_(
                        ObjectiveProgress.objective_id == LearningObjective.id,
                        ObjectiveProgress.user_id == enrolment.student_id,
                    ),
                )
                .where(
                    Subtopic.topic_id == topic_id,
                    Subtopic.retired_at.is_(None),
                    LearningObjective.retired_at.is_(None),
                    on_tier(enrolment.tier),
                )
                .order_by(Subtopic.position, LearningObjective.position)
            )
        ).all()
        return [(objective_id, level or 1) for objective_id, level in rows]

    async def _complete(self, challenge: Challenge, *, grant_badges: bool = True) -> int:
        """Score and close the challenge, award its bonus XP and badges. Idempotent.

        Args:
            challenge: The locked challenge.
            grant_badges: False when the caller grants badges itself (answering
                reports new badges in its response).

        Returns:
            Bonus XP awarded now (0 if it was already completed).
        """
        if challenge.status is ChallengeStatus.COMPLETED:
            return 0
        rows = (
            await self._session.execute(
                select(PracticeItem, Question.marks)
                .join(Question, Question.id == PracticeItem.question_id)
                .where(PracticeItem.challenge_id == challenge.id)
            )
        ).all()
        if challenge.kind is ChallengeKind.DAILY:
            score = sum(1 for item, _ in rows if item.correct)
            max_score = len(rows)
        else:
            score = sum(marks_earned(item, marks) for item, marks in rows)
            max_score = sum(marks for _, marks in rows)
        challenge.score = score
        challenge.max_score = max_score
        challenge.percent = round(100 * score / max_score, 1) if max_score else 0.0
        challenge.status = ChallengeStatus.COMPLETED
        challenge.completed_at = self._now
        await self._session.flush()
        if challenge.kind is ChallengeKind.DAILY:
            bonus = await self._rewards.award(
                challenge.user_id, XpSource.DAILY_CHALLENGE, challenge.id, DAILY_CHALLENGE_BONUS
            )
            exam_ready = False
        else:
            bonus = await self._rewards.award(
                challenge.user_id, XpSource.BOSS_BATTLE, challenge.id, boss_bonus(challenge.percent)
            )
            enrolment = await self._session.get(StudentSubject, challenge.enrolment_id)
            exam_ready = (
                enrolment is not None
                and challenge.topic_id is not None
                and await self.exam_ready_reached(enrolment, challenge.topic_id)
            )
        if grant_badges:
            await self._rewards.grant_badges(challenge.user_id, exam_ready_topic=exam_ready)
        logger.info(
            "challenge_completed",
            extra={"challenge_kind": challenge.kind.value, "percent": challenge.percent},
        )
        return bonus

    async def _out(self, challenge: Challenge) -> ChallengeOut:
        total, answered = await self._counts(challenge.id)
        topic_title = (
            await self._session.scalar(select(Topic.title).where(Topic.id == challenge.topic_id))
            if challenge.topic_id
            else None
        )
        seconds_left = (
            max(0, int((challenge.deadline_at - self._now).total_seconds()))
            if challenge.deadline_at and challenge.status is ChallengeStatus.ACTIVE
            else None
        )
        out = ChallengeOut(
            id=challenge.id,
            kind=challenge.kind,
            status=challenge.status,
            london_date=challenge.london_date,
            total=total,
            answered=answered,
            enrolment_id=challenge.enrolment_id,
            topic_id=challenge.topic_id,
            topic_title=topic_title,
            deadline_at=challenge.deadline_at,
            seconds_left=seconds_left,
            score=challenge.score,
            max_score=challenge.max_score,
            percent=challenge.percent,
            bonus_xp=None,
            grade=None,
            previous_best=None,
            personal_best=False,
            results=[],
        )
        if challenge.status is ChallengeStatus.COMPLETED:
            await self._add_results(challenge, out)
        return out

    async def _add_results(self, challenge: Challenge, out: ChallengeOut) -> None:
        bonus_source = (
            XpSource.DAILY_CHALLENGE
            if challenge.kind is ChallengeKind.DAILY
            else XpSource.BOSS_BATTLE
        )
        out.bonus_xp = await self._session.scalar(
            select(XpEvent.amount).where(
                XpEvent.user_id == challenge.user_id,
                XpEvent.source == bonus_source,
                XpEvent.ref_id == challenge.id,
            )
        )
        rows = (
            await self._session.execute(
                select(PracticeItem, Question)
                .join(Question, Question.id == PracticeItem.question_id)
                .where(PracticeItem.challenge_id == challenge.id)
                .order_by(PracticeItem.position)
            )
        ).all()
        for item, question in rows:
            answered = item.answered_at is not None
            stored = (item.response or {}).get("result", {})
            out.results.append(
                ChallengeItemResultOut(
                    position=item.position or 0,
                    stem=question.stem,
                    marks=question.marks,
                    marks_earned=marks_earned(item, question.marks),
                    answered=answered,
                    correct=item.correct,
                    your_answer=(item.response or {}).get("answer") if answered else None,
                    correct_answer=stored.get("correctAnswer")
                    or mark(
                        question.question_type, question.answer, question.options, ""
                    ).correct_answer_display,
                    worked_solution=question.worked_solution,
                )
            )
        if challenge.kind is ChallengeKind.BOSS and challenge.percent is not None:
            out.grade = await self._grade(challenge, challenge.percent)
            out.previous_best = await self._session.scalar(
                select(func.max(Challenge.percent)).where(
                    Challenge.user_id == challenge.user_id,
                    Challenge.kind == ChallengeKind.BOSS,
                    Challenge.topic_id == challenge.topic_id,
                    Challenge.status == ChallengeStatus.COMPLETED,
                    Challenge.id != challenge.id,
                    Challenge.completed_at <= challenge.completed_at,
                )
            )
            out.personal_best = out.previous_best is None or challenge.percent > out.previous_best

    async def _grade(self, challenge: Challenge, percent: float) -> GradeEstimateOut:
        enrolment = await self._session.get(StudentSubject, challenge.enrolment_id)
        boundaries: dict[int, float] = {}
        if enrolment is not None and enrolment.specification_id is not None:
            tier_match = (
                GradeBoundary.tier.is_(None)
                if enrolment.tier is None
                else GradeBoundary.tier == enrolment.tier
            )
            boundaries = {
                grade: minimum
                for grade, minimum in (
                    await self._session.execute(
                        select(GradeBoundary.grade, GradeBoundary.min_percent).where(
                            GradeBoundary.specification_id == enrolment.specification_id,
                            tier_match,
                        )
                    )
                ).all()
            }
        result = estimate(percent, boundaries)
        return GradeEstimateOut(
            percent=result.percent,
            standing=result.standing,
            band_low=result.band_low,
            band_high=result.band_high,
            below_lowest_grade=result.below_lowest_grade,
        )
