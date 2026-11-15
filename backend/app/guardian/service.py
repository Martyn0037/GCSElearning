# backend/app/guardian/service.py
"""Guardian use cases. Guardians see only students linked to them; anything
else is 404 (ADR-007). Everything is read-only except consent and deletion."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Date, case, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import audit
from app.auth.passwords import verify_password
from app.core.errors import InvalidRequestError, NotFoundError
from app.gamification import badges as badge_rules
from app.gamification.standings import topic_standings
from app.gamification.streaks import StreakState, current_streak, week_start
from app.guardian.schemas import (
    CONSENT_TYPE,
    PRIVACY_POLICY_VERSION,
    BossResultOut,
    ConsentOut,
    LinkedStudentOut,
    SubjectWeekOut,
    WeakTopicOut,
    WeeklySummaryOut,
)
from app.models.consent import Consent
from app.models.curriculum import Subject, Topic
from app.models.enrolment import StudentSetText, StudentSubject, StudentTopicSetting
from app.models.gamification import (
    Challenge,
    ChallengeKind,
    ChallengeStatus,
    Streak,
    UserBadge,
    XpEvent,
)
from app.models.learning import TutorMessage
from app.models.question import Mistake, ObjectiveProgress, PracticeItem
from app.models.user import GuardianLink, User
from app.practice.review import LONDON, london_today

MAX_WEEKS_BACK = 11
# Time on one question is capped, so a question left open overnight doesn't count.
MINUTES_CAP = timedelta(minutes=10)
WEAK_TOPICS = 3


class GuardianService:
    """Guardian use cases for one request. Mutating methods commit."""

    def __init__(self, session: AsyncSession, now: datetime) -> None:
        """Create the service."""
        self._session = session
        self._now = now

    async def students(self, guardian_id: uuid.UUID) -> list[LinkedStudentOut]:
        """Students linked to this guardian, with consent status."""
        rows = (
            await self._session.scalars(
                select(User)
                .join(GuardianLink, GuardianLink.student_id == User.id)
                .where(GuardianLink.guardian_id == guardian_id)
                .order_by(User.display_name)
            )
        ).all()
        return [
            LinkedStudentOut(
                id=s.id,
                display_name=s.display_name,
                consent=await self._consent(guardian_id, s.id),
                current_policy_version=PRIVACY_POLICY_VERSION,
            )
            for s in rows
        ]

    async def _student(self, guardian_id: uuid.UUID, student_id: uuid.UUID) -> User:
        linked = await self._session.scalar(
            select(GuardianLink.student_id).where(
                GuardianLink.guardian_id == guardian_id, GuardianLink.student_id == student_id
            )
        )
        student = await self._session.get(User, student_id) if linked else None
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def _consent(self, guardian_id: uuid.UUID, student_id: uuid.UUID) -> ConsentOut:
        row = await self._session.scalar(
            select(Consent)
            .where(
                Consent.guardian_id == guardian_id,
                Consent.student_id == student_id,
                Consent.consent_type == CONSENT_TYPE,
                Consent.withdrawn_at.is_(None),
            )
            .order_by(Consent.granted_at.desc())
            .limit(1)
        )
        if row is None:
            return ConsentOut(granted=False, policy_version=None, granted_at=None)
        return ConsentOut(
            granted=True, policy_version=row.policy_version, granted_at=row.granted_at
        )

    async def give_consent(
        self, guardian_id: uuid.UUID, student_id: uuid.UUID, policy_version: str
    ) -> ConsentOut:
        """Record consent under the current privacy notice. Idempotent.

        Raises:
            InvalidRequestError: ``POLICY_OUT_OF_DATE`` for an older notice.
        """
        await self._student(guardian_id, student_id)
        if policy_version != PRIVACY_POLICY_VERSION:
            raise InvalidRequestError(
                "Please read the current privacy notice first.", code="POLICY_OUT_OF_DATE"
            )
        current = await self._consent(guardian_id, student_id)
        if current.granted and current.policy_version == policy_version:
            return current
        self._session.add(
            Consent(
                student_id=student_id,
                guardian_id=guardian_id,
                consent_type=CONSENT_TYPE,
                policy_version=policy_version,
                granted_at=self._now,
            )
        )
        audit.record(
            self._session,
            action="consent.granted",
            now=self._now,
            actor_user_id=guardian_id,
            target_user_id=student_id,
            details={"policy_version": policy_version},
        )
        await self._session.commit()
        return await self._consent(guardian_id, student_id)

    async def withdraw_consent(self, guardian_id: uuid.UUID, student_id: uuid.UUID) -> ConsentOut:
        """Withdraw consent (the record is kept, marked withdrawn). Idempotent."""
        await self._student(guardian_id, student_id)
        rows = (
            await self._session.scalars(
                select(Consent).where(
                    Consent.guardian_id == guardian_id,
                    Consent.student_id == student_id,
                    Consent.withdrawn_at.is_(None),
                )
            )
        ).all()
        for row in rows:
            row.withdrawn_at = self._now
        if rows:
            audit.record(
                self._session,
                action="consent.withdrawn",
                now=self._now,
                actor_user_id=guardian_id,
                target_user_id=student_id,
            )
        await self._session.commit()
        return await self._consent(guardian_id, student_id)

    async def weekly_summary(
        self, guardian_id: uuid.UUID, student_id: uuid.UUID, weeks_ago: int
    ) -> WeeklySummaryOut:
        """One London week of the student's activity."""
        student = await self._student(guardian_id, student_id)
        start_day = week_start(london_today(self._now)) - timedelta(weeks=weeks_ago)
        end_day = start_day + timedelta(days=6)
        start = datetime.combine(start_day, time(), LONDON)
        end = start + timedelta(days=7)
        in_week = (PracticeItem.answered_at >= start, PracticeItem.answered_at < end)
        local_day = cast(func.timezone(LONDON.key, PracticeItem.answered_at), Date)
        spent = func.least(PracticeItem.answered_at - PracticeItem.served_at, MINUTES_CAP)
        answered, correct, seconds = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count(case((PracticeItem.correct.is_(True), 1))),
                    func.coalesce(func.sum(func.extract("epoch", spent)), 0),
                ).where(PracticeItem.user_id == student_id, *in_week)
            )
        ).one()
        days = (
            await self._session.scalars(
                select(local_day)
                .where(PracticeItem.user_id == student_id, *in_week)
                .group_by(local_day)
                .order_by(local_day)
            )
        ).all()
        xp = await self._session.scalar(
            select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
                XpEvent.user_id == student_id, XpEvent.created_at >= start, XpEvent.created_at < end
            )
        )
        fixed = await self._session.scalar(
            select(func.count())
            .select_from(Mistake)
            .where(
                Mistake.user_id == student_id,
                Mistake.resolved_at >= start,
                Mistake.resolved_at < end,
            )
        )
        badge_codes = (
            await self._session.scalars(
                select(UserBadge.badge_code).where(
                    UserBadge.user_id == student_id,
                    UserBadge.awarded_at >= start,
                    UserBadge.awarded_at < end,
                )
            )
        ).all()
        bosses = (
            await self._session.execute(
                select(Topic.title, Challenge.percent)
                .outerjoin(Topic, Topic.id == Challenge.topic_id)
                .where(
                    Challenge.user_id == student_id,
                    Challenge.kind == ChallengeKind.BOSS,
                    Challenge.status == ChallengeStatus.COMPLETED,
                    Challenge.completed_at >= start,
                    Challenge.completed_at < end,
                )
                .order_by(Challenge.completed_at)
            )
        ).all()
        streak = await self._session.get(Streak, student_id)
        state = (
            StreakState(
                streak.current_days,
                streak.longest_days,
                streak.last_active_on,
                streak.freeze_used_week,
            )
            if streak
            else StreakState()
        )
        return WeeklySummaryOut(
            student_id=student.id,
            display_name=student.display_name,
            week_start=start_day,
            week_end=end_day,
            answered=answered,
            correct=correct,
            minutes=round(float(seconds) / 60),
            active_days=list(days),
            xp=int(xp or 0),
            streak_days=current_streak(state, min(end_day, london_today(self._now))),
            mistakes_fixed=int(fixed or 0),
            badges=[badge_rules.BY_CODE[c].name for c in badge_codes if c in badge_rules.BY_CODE],
            boss_battles=[BossResultOut(topic_title=t, percent=p) for t, p in bosses],
            subjects=await self._subjects(student_id, start, end),
        )

    async def _subjects(
        self, student_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[SubjectWeekOut]:
        enrolments = (
            await self._session.execute(
                select(StudentSubject, Subject.name)
                .join(Subject, Subject.id == StudentSubject.subject_id)
                .where(
                    StudentSubject.student_id == student_id,
                    StudentSubject.specification_id.is_not(None),
                )
                .order_by(StudentSubject.position)
            )
        ).all()
        counts = {
            enrolment_id: (n, c)
            for enrolment_id, n, c in (
                await self._session.execute(
                    select(
                        PracticeItem.enrolment_id,
                        func.count(),
                        func.count(case((PracticeItem.correct.is_(True), 1))),
                    )
                    .where(
                        PracticeItem.user_id == student_id,
                        PracticeItem.answered_at >= start,
                        PracticeItem.answered_at < end,
                    )
                    .group_by(PracticeItem.enrolment_id)
                )
            ).all()
        }
        out = []
        for enrolment, name in enrolments:
            standings = await topic_standings(self._session, enrolment)
            titles = dict(
                (
                    await self._session.execute(
                        select(Topic.id, Topic.title).where(Topic.id.in_(list(standings)))
                    )
                ).all()
            )
            practised = [
                (s.mastery, topic_id, s)
                for topic_id, s in standings.items()
                if s.objectives_practised
            ]
            practised.sort(key=lambda entry: entry[0])
            weak = [
                WeakTopicOut(title=titles.get(topic_id, ""), mastery=s.mastery, ring=s.ring)
                for _, topic_id, s in practised[:WEAK_TOPICS]
            ]
            n, c = counts.get(enrolment.id, (0, 0))
            out.append(SubjectWeekOut(subject_name=name, answered=n, correct=c, weak_topics=weak))
        return out

    async def export(self, guardian_id: uuid.UUID, student_id: uuid.UUID) -> dict[str, Any]:
        """Everything stored about the student, as JSON (UK GDPR access request)."""
        student = await self._student(guardian_id, student_id)

        async def rows(model: Any, *where: Any) -> list[dict[str, Any]]:
            items = (await self._session.scalars(select(model).where(*where))).all()
            return [
                {c.key: _plain(getattr(item, c.key)) for c in model.__table__.columns}
                for item in items
            ]

        audit.record(
            self._session,
            action="data.exported",
            now=self._now,
            actor_user_id=guardian_id,
            target_user_id=student_id,
        )
        await self._session.commit()
        return {
            "exported_at": self._now.isoformat(),
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "student": {
                "id": str(student.id),
                "display_name": student.display_name,
                "username": student.username,
                "created_at": student.created_at.isoformat(),
            },
            "subjects": await rows(StudentSubject, StudentSubject.student_id == student_id),
            "set_texts": await rows(
                StudentSetText,
                StudentSetText.student_subject_id.in_(
                    select(StudentSubject.id).where(StudentSubject.student_id == student_id)
                ),
            ),
            "topic_settings": await rows(
                StudentTopicSetting, StudentTopicSetting.student_id == student_id
            ),
            "answers": await rows(PracticeItem, PracticeItem.user_id == student_id),
            "mistakes": await rows(Mistake, Mistake.user_id == student_id),
            "skill_progress": await rows(
                ObjectiveProgress, ObjectiveProgress.user_id == student_id
            ),
            "xp": await rows(XpEvent, XpEvent.user_id == student_id),
            "badges": await rows(UserBadge, UserBadge.user_id == student_id),
            "challenges": await rows(Challenge, Challenge.user_id == student_id),
            "streak": await rows(Streak, Streak.user_id == student_id),
            "tutor_messages": await rows(TutorMessage, TutorMessage.user_id == student_id),
            "consents": await rows(Consent, Consent.student_id == student_id),
        }

    async def delete_student(self, guardian: User, student_id: uuid.UUID, password: str) -> None:
        """Permanently delete the student's account and every record about them.

        The guardian re-enters their password. The audit event keeps only IDs.

        Raises:
            NotFoundError: Not a linked student.
            InvalidRequestError: ``WRONG_PASSWORD``.
        """
        await self._student(guardian.id, student_id)
        if not verify_password(guardian.password_hash, password):
            raise InvalidRequestError("That password isn't right.", code="WRONG_PASSWORD")
        await self._session.execute(delete(User).where(User.id == student_id))
        audit.record(
            self._session,
            action="student.deleted",
            now=self._now,
            actor_user_id=guardian.id,
            details={"student_id": str(student_id)},
        )
        await self._session.commit()


def _plain(value: Any) -> Any:
    """JSON-friendly value."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value"):  # enums
        return value.value
    if value.__class__.__name__ == "Decimal":
        return str(value)
    return value
