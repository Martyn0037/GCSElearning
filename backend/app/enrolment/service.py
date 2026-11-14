# backend/app/enrolment/service.py
"""Subject choice, topic maps and the admin's enrolment tools.

Rules (ADR-012):
- A subject is *active* only once matched to an imported, current spec for its
  board. Until then it's *pending* and gets no questions.
- "I don't know" for the board uses the subject's most common board and leaves
  ``board_confirmed`` false; "not sure" for the tier uses Higher and leaves
  ``tier_confirmed`` false. The admin can confirm or correct both.
- Typed-in subjects and set texts stay pending until the admin matches them.

Every list is loaded with a fixed number of batched queries (no N+1).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.core.pagination import Cursor
from app.enrolment.schemas import (
    AdminEnrolmentOut,
    AdminEnrolmentPage,
    AdminSpecificationOut,
    AttentionReason,
    BoardOut,
    CatalogueOut,
    CatalogueSpecificationOut,
    CatalogueSubjectOut,
    EnrolmentOut,
    EnrolmentStatus,
    EnrolmentUpdate,
    SetTextOptionOut,
    SpecificationOut,
    StudentSetTextOut,
    SubjectChoice,
    SubjectChoices,
    SubtopicOut,
    TopicMapOut,
    TopicOut,
)
from app.models.curriculum import (
    ExamBoard,
    LearningObjective,
    SetTextOption,
    Specification,
    Subject,
    Subtopic,
    Tier,
    Topic,
)
from app.models.enrolment import StudentSetText, StudentSubject, StudentTopicSetting
from app.models.user import User


def _spec_out(spec: Specification) -> SpecificationOut:
    return SpecificationOut(
        id=spec.id,
        board_id=spec.board_id,
        code=spec.code,
        title=spec.title,
        version=spec.version,
        tiered=spec.tiered,
    )


async def load_catalogue(session: AsyncSession) -> CatalogueOut:
    """Return boards, subjects and current specs (with set-text lists) in 4 queries."""
    boards = (await session.scalars(select(ExamBoard).order_by(ExamBoard.position))).all()
    subjects = (await session.scalars(select(Subject).order_by(Subject.position))).all()
    specs = (
        await session.scalars(
            select(Specification)
            .where(Specification.is_current.is_(True))
            .order_by(Specification.code)
        )
    ).all()
    options = (
        await session.scalars(
            select(SetTextOption)
            .where(
                SetTextOption.specification_id.in_([s.id for s in specs]),
                SetTextOption.retired_at.is_(None),
            )
            .order_by(SetTextOption.position)
        )
    ).all()
    options_by_spec: dict[uuid.UUID, list[SetTextOptionOut]] = defaultdict(list)
    for option in options:
        options_by_spec[option.specification_id].append(SetTextOptionOut.model_validate(option))
    specs_by_subject: dict[uuid.UUID, list[CatalogueSpecificationOut]] = defaultdict(list)
    for spec in specs:
        specs_by_subject[spec.subject_id].append(
            CatalogueSpecificationOut(
                **_spec_out(spec).model_dump(), set_texts=options_by_spec[spec.id]
            )
        )
    return CatalogueOut(
        boards=[BoardOut.model_validate(b) for b in boards],
        subjects=[
            CatalogueSubjectOut(
                id=s.id,
                slug=s.slug,
                name=s.name,
                has_tiers=s.has_tiers,
                set_text_categories=list(s.set_text_categories),
                most_common_board_id=s.most_common_board_id,
                specifications=specs_by_subject[s.id],
            )
            for s in subjects
        ],
    )


class EnrolmentService:
    """Enrolment use cases for one request. Public mutating methods commit."""

    def __init__(self, session: AsyncSession, now: datetime) -> None:
        """Create the service.

        Args:
            session: Database session for this request.
            now: The request's current time (UTC).
        """
        self._session = session
        self._now = now

    # ------------------------------------------------------------ student

    async def list_for_student(self, student_id: uuid.UUID) -> list[EnrolmentOut]:
        """Return the student's subjects in the order they chose them."""
        rows = (
            await self._session.scalars(
                select(StudentSubject)
                .where(StudentSubject.student_id == student_id)
                .order_by(StudentSubject.position)
            )
        ).all()
        return [
            EnrolmentOut(**item.model_dump(exclude={"student_id", "student_name", "attention"}))
            for item in await self._describe(rows, {})
        ]

    async def replace_choices(self, student: User, choices: SubjectChoices) -> list[EnrolmentOut]:
        """Replace the student's subjects with ``choices`` (idempotent).

        Subjects kept from before keep their pinned spec version unless their
        board changes. Subjects left out are removed with their set texts.

        Raises:
            InvalidRequestError: If a choice refers to an unknown subject, board,
                tier, category or set-text option, or repeats a subject.
        """
        _reject_duplicates(choices.subjects)
        # Serialise concurrent saves for the same student (e.g. a double tap):
        # the second waits, then sees the first one's rows.
        await self._session.execute(select(User.id).where(User.id == student.id).with_for_update())
        subject_ids = {c.subject_id for c in choices.subjects if c.subject_id}
        subjects = {
            s.id: s
            for s in (
                await self._session.scalars(select(Subject).where(Subject.id.in_(subject_ids)))
            ).all()
        }
        if missing := subject_ids - subjects.keys():
            raise InvalidRequestError(f"Unknown subject: {sorted(map(str, missing))[0]}")
        board_ids = {c.board_id for c in choices.subjects if c.board_id}
        known_boards = set(
            (
                await self._session.scalars(select(ExamBoard.id).where(ExamBoard.id.in_(board_ids)))
            ).all()
        )
        if board_ids - known_boards:
            raise InvalidRequestError("Unknown exam board")

        existing = (
            await self._session.scalars(
                select(StudentSubject)
                .where(StudentSubject.student_id == student.id)
                .with_for_update()
            )
        ).all()
        by_key = {_enrolment_key(e.subject_id, e.custom_subject_name): e for e in existing}
        kept: set[uuid.UUID] = set()

        for position, choice in enumerate(choices.subjects):
            subject = subjects.get(choice.subject_id) if choice.subject_id else None
            enrolment = by_key.get(_enrolment_key(choice.subject_id, choice.custom_name))
            board_id, board_confirmed = _resolve_board(choice, subject)
            tier, tier_confirmed = _resolve_tier(choice, subject)
            if enrolment is None:
                enrolment = StudentSubject(
                    id=uuid.uuid4(),
                    student_id=student.id,
                    subject_id=choice.subject_id,
                    custom_subject_name=choice.custom_name,
                )
                self._session.add(enrolment)
            elif enrolment.board_id != board_id:
                enrolment.specification_id = None  # board changed: re-match below
            enrolment.board_id = board_id
            enrolment.board_confirmed = board_confirmed
            enrolment.tier = tier
            enrolment.tier_confirmed = tier_confirmed
            enrolment.position = position
            if enrolment.specification_id is None and subject is not None and board_id:
                enrolment.specification_id = await self._current_spec_id(subject.id, board_id)
            await self._session.flush()
            await self._replace_set_texts(enrolment, subject, choice)
            kept.add(enrolment.id)

        removed = [e.id for e in existing if e.id not in kept]
        if removed:
            await self._session.execute(
                delete(StudentSubject).where(StudentSubject.id.in_(removed))
            )
        if student.setup_completed_at is None:
            student.setup_completed_at = self._now
        await self._session.commit()
        return await self.list_for_student(student.id)

    async def _replace_set_texts(
        self, enrolment: StudentSubject, subject: Subject | None, choice: SubjectChoice
    ) -> None:
        allowed_categories = set(subject.set_text_categories) if subject else set()
        option_ids = {t.option_id for t in choice.set_texts if t.option_id}
        options = {
            o.id: o
            for o in (
                await self._session.scalars(
                    select(SetTextOption).where(
                        SetTextOption.id.in_(option_ids), SetTextOption.retired_at.is_(None)
                    )
                )
            ).all()
        }
        await self._session.execute(
            delete(StudentSetText).where(StudentSetText.student_subject_id == enrolment.id)
        )
        for position, text_choice in enumerate(choice.set_texts):
            if subject is not None and text_choice.category not in allowed_categories:
                raise InvalidRequestError(
                    f"{subject.name} has no set-text category {text_choice.category!r}"
                )
            if text_choice.option_id is not None:
                option = options.get(text_choice.option_id)
                if (
                    option is None
                    or option.specification_id != enrolment.specification_id
                    or option.category != text_choice.category
                ):
                    raise InvalidRequestError("That set text isn't on this board's list")
            self._session.add(
                StudentSetText(
                    id=uuid.uuid4(),
                    student_subject_id=enrolment.id,
                    category=text_choice.category,
                    set_text_option_id=text_choice.option_id,
                    custom_title=text_choice.custom_title,
                    custom_author=text_choice.custom_author,
                    position=position,
                )
            )

    async def get_for_student(
        self, student_id: uuid.UUID, enrolment_id: uuid.UUID
    ) -> StudentSubject:
        """Return one of the student's enrolments.

        Raises:
            NotFoundError: If it doesn't exist or belongs to someone else.
        """
        enrolment = await self._session.get(StudentSubject, enrolment_id)
        if enrolment is None or enrolment.student_id != student_id:
            raise NotFoundError("Subject not found")
        return enrolment

    async def topic_map(self, enrolment: StudentSubject) -> TopicMapOut:
        """Build the topic map for an active enrolment, in the student's order.

        A topic is unlocked once it's marked as covered at school. Objective
        counts include only statements on the student's tier.

        Raises:
            ConflictError: If the subject is still pending (no spec yet).
        """
        if enrolment.specification_id is None:
            raise ConflictError("This subject is still being set up.", code="SUBJECT_NOT_READY")
        spec = await self._session.get(Specification, enrolment.specification_id)
        assert spec is not None  # noqa: S101 - FK guarantees it
        topics = (
            await self._session.scalars(
                select(Topic).where(Topic.specification_id == spec.id, Topic.retired_at.is_(None))
            )
        ).all()
        settings = {
            s.topic_id: s
            for s in (
                await self._session.scalars(
                    select(StudentTopicSetting).where(
                        StudentTopicSetting.student_id == enrolment.student_id,
                        StudentTopicSetting.topic_id.in_([t.id for t in topics]),
                    )
                )
            ).all()
        }
        on_tier = (
            LearningObjective.foundation_text.is_not(None)
            if enrolment.tier is not Tier.HIGHER
            else LearningObjective.id.is_not(None)
        )
        subtopic_rows = (
            await self._session.execute(
                select(Subtopic, func.count(LearningObjective.id))
                .outerjoin(
                    LearningObjective,
                    and_(
                        LearningObjective.subtopic_id == Subtopic.id,
                        LearningObjective.retired_at.is_(None),
                        on_tier,
                    ),
                )
                .where(Subtopic.topic_id.in_([t.id for t in topics]), Subtopic.retired_at.is_(None))
                .group_by(Subtopic.id)
                .order_by(Subtopic.position)
            )
        ).all()
        subtopics_by_topic: dict[uuid.UUID, list[SubtopicOut]] = defaultdict(list)
        for subtopic, count in subtopic_rows:
            subtopics_by_topic[subtopic.topic_id].append(
                SubtopicOut(id=subtopic.id, title=subtopic.title, objective_count=count)
            )

        def order_key(topic: Topic) -> tuple[int, int]:
            setting = settings.get(topic.id)
            override = setting.sort_order if setting and setting.sort_order is not None else None
            return (override if override is not None else topic.position, topic.position)

        topic_outs = []
        for topic in sorted(topics, key=order_key):
            taught = bool(settings.get(topic.id) and settings[topic.id].taught_at_school)
            topic_outs.append(
                TopicOut(
                    id=topic.id,
                    ref=topic.ref,
                    title=topic.title,
                    taught_at_school=taught,
                    unlocked=taught,
                    subtopics=subtopics_by_topic[topic.id],
                )
            )
        subject_name = await self._subject_name(enrolment)
        return TopicMapOut(
            enrolment_id=enrolment.id,
            subject_name=subject_name,
            tier=enrolment.tier,
            specification=_spec_out(spec),
            topics=topic_outs,
        )

    # ------------------------------------------------------------ admin

    async def admin_list(
        self, *, attention_only: bool, limit: int, cursor: Cursor | None
    ) -> AdminEnrolmentPage:
        """Page through all students' enrolments, oldest first.

        With ``attention_only``, only enrolments needing the admin: no spec,
        unconfirmed board/tier, or a pending set text.
        """
        query = select(StudentSubject).order_by(StudentSubject.created_at, StudentSubject.id)
        if cursor is not None:
            query = query.where(
                tuple_(StudentSubject.created_at, StudentSubject.id)
                > tuple_(cursor.created_at, cursor.id)
            )
        if attention_only:
            pending_text = (
                select(StudentSetText.id)
                .where(
                    StudentSetText.student_subject_id == StudentSubject.id,
                    StudentSetText.set_text_option_id.is_(None),
                )
                .exists()
            )
            query = query.where(
                or_(
                    StudentSubject.specification_id.is_(None),
                    StudentSubject.board_confirmed.is_(False),
                    StudentSubject.tier_confirmed.is_(False),
                    pending_text,
                )
            )
        rows = (await self._session.scalars(query.limit(limit + 1))).all()
        page, extra = rows[:limit], rows[limit:]
        students = {
            u.id: u.display_name
            for u in (
                await self._session.scalars(
                    select(User).where(User.id.in_({e.student_id for e in page}))
                )
            ).all()
        }
        items = await self._describe(page, students)
        next_cursor = Cursor(page[-1].created_at, page[-1].id).encode() if extra else None
        return AdminEnrolmentPage(items=items, next_cursor=next_cursor)

    async def admin_get(self, enrolment_id: uuid.UUID) -> StudentSubject:
        """Return any enrolment.

        Raises:
            NotFoundError: If it doesn't exist.
        """
        enrolment = await self._session.get(StudentSubject, enrolment_id)
        if enrolment is None:
            raise NotFoundError("Enrolment not found")
        return enrolment

    async def admin_update(
        self, enrolment_id: uuid.UUID, update: EnrolmentUpdate
    ) -> AdminEnrolmentOut:
        """Correct or confirm an enrolment's board, tier or spec version.

        Choosing a spec for a typed-in subject converts it into that catalogue
        subject.

        Raises:
            NotFoundError: If the enrolment, board or spec doesn't exist.
            InvalidRequestError: If the spec doesn't fit the subject or board.
            ConflictError: If converting would duplicate a subject the student has.
        """
        enrolment = await self.admin_get(enrolment_id)
        spec: Specification | None = None
        if update.specification_id is not None:
            spec = await self._session.get(Specification, update.specification_id)
            if spec is None:
                raise NotFoundError("Specification not found")
            if enrolment.subject_id is not None and spec.subject_id != enrolment.subject_id:
                raise InvalidRequestError("That specification is for a different subject")
            if update.board_id is not None and update.board_id != spec.board_id:
                raise InvalidRequestError("That specification is for a different board")
        if (
            update.board_id is not None
            and await self._session.get(ExamBoard, update.board_id) is None
        ):
            raise NotFoundError("Exam board not found")

        if spec is not None:
            if enrolment.subject_id is None:
                clash = await self._session.scalar(
                    select(StudentSubject.id).where(
                        StudentSubject.student_id == enrolment.student_id,
                        StudentSubject.subject_id == spec.subject_id,
                    )
                )
                if clash is not None:
                    raise ConflictError("The student already has that subject")
                enrolment.subject_id = spec.subject_id
                enrolment.custom_subject_name = None
            if enrolment.specification_id != spec.id:
                await self._drop_set_text_options(enrolment.id)
            enrolment.specification_id = spec.id
            enrolment.board_id = spec.board_id
            enrolment.board_confirmed = True
        elif update.board_id is not None:
            if update.board_id != enrolment.board_id:
                await self._drop_set_text_options(enrolment.id)
                enrolment.specification_id = (
                    await self._current_spec_id(enrolment.subject_id, update.board_id)
                    if enrolment.subject_id
                    else None
                )
            enrolment.board_id = update.board_id
            enrolment.board_confirmed = True
        if update.tier is not None:
            enrolment.tier = update.tier
            enrolment.tier_confirmed = True
        await self._session.commit()
        return await self._admin_one(enrolment)

    async def admin_match_set_text(
        self, set_text_id: uuid.UUID, option_id: uuid.UUID
    ) -> AdminEnrolmentOut:
        """Match a typed-in set text to an option on the board's list.

        Raises:
            NotFoundError: If the set text or option doesn't exist.
            InvalidRequestError: If the option isn't on the enrolment's spec.
        """
        item = await self._session.get(StudentSetText, set_text_id)
        if item is None:
            raise NotFoundError("Set text not found")
        enrolment = await self.admin_get(item.student_subject_id)
        option = await self._session.get(SetTextOption, option_id)
        if option is None:
            raise NotFoundError("Set text option not found")
        if option.specification_id != enrolment.specification_id:
            raise InvalidRequestError("That option isn't on this subject's specification")
        item.set_text_option_id = option.id
        item.category = option.category
        await self._session.commit()
        return await self._admin_one(enrolment)

    async def admin_delete_set_text(self, set_text_id: uuid.UUID) -> None:
        """Remove a set text (e.g. a typo the student made). Idempotent."""
        await self._session.execute(delete(StudentSetText).where(StudentSetText.id == set_text_id))
        await self._session.commit()

    async def set_topic_taught(
        self, enrolment: StudentSubject, topic_id: uuid.UUID, taught: bool
    ) -> TopicMapOut:
        """Mark a topic as covered (or not) at school for this student."""
        await self._require_topic(enrolment, topic_id)
        await self._session.execute(
            insert(StudentTopicSetting)
            .values(student_id=enrolment.student_id, topic_id=topic_id, taught_at_school=taught)
            .on_conflict_do_update(
                index_elements=[StudentTopicSetting.student_id, StudentTopicSetting.topic_id],
                set_={"taught_at_school": taught},
            )
        )
        await self._session.commit()
        return await self.topic_map(enrolment)

    async def set_topic_order(
        self, enrolment: StudentSubject, topic_ids: Sequence[uuid.UUID]
    ) -> TopicMapOut:
        """Set the order of every topic in this enrolment's spec.

        Raises:
            InvalidRequestError: If ``topic_ids`` isn't exactly the spec's topics.
        """
        if enrolment.specification_id is None:
            raise ConflictError("This subject is still being set up.", code="SUBJECT_NOT_READY")
        current = set(
            (
                await self._session.scalars(
                    select(Topic.id).where(
                        Topic.specification_id == enrolment.specification_id,
                        Topic.retired_at.is_(None),
                    )
                )
            ).all()
        )
        if len(topic_ids) != len(set(topic_ids)) or set(topic_ids) != current:
            raise InvalidRequestError("Give every topic of this subject exactly once")
        for position, topic_id in enumerate(topic_ids):
            await self._session.execute(
                insert(StudentTopicSetting)
                .values(student_id=enrolment.student_id, topic_id=topic_id, sort_order=position)
                .on_conflict_do_update(
                    index_elements=[StudentTopicSetting.student_id, StudentTopicSetting.topic_id],
                    set_={"sort_order": position},
                )
            )
        await self._session.commit()
        return await self.topic_map(enrolment)

    async def list_specifications(self) -> list[AdminSpecificationOut]:
        """All imported specs with topic/objective counts (bounded: one row per spec version)."""
        topic_counts = (
            select(Topic.specification_id, func.count(Topic.id).label("n"))
            .where(Topic.retired_at.is_(None))
            .group_by(Topic.specification_id)
            .subquery()
        )
        objective_counts = (
            select(LearningObjective.specification_id, func.count(LearningObjective.id).label("n"))
            .where(LearningObjective.retired_at.is_(None))
            .group_by(LearningObjective.specification_id)
            .subquery()
        )
        rows = (
            await self._session.execute(
                select(
                    Specification,
                    Subject.name,
                    ExamBoard.name,
                    func.coalesce(topic_counts.c.n, 0),
                    func.coalesce(objective_counts.c.n, 0),
                )
                .join(Subject, Subject.id == Specification.subject_id)
                .join(ExamBoard, ExamBoard.id == Specification.board_id)
                .outerjoin(topic_counts, topic_counts.c.specification_id == Specification.id)
                .outerjoin(
                    objective_counts, objective_counts.c.specification_id == Specification.id
                )
                .order_by(Subject.position, ExamBoard.position, Specification.version)
            )
        ).all()
        return [
            AdminSpecificationOut(
                **_spec_out(spec).model_dump(),
                subject_name=subject_name,
                board_name=board_name,
                is_current=spec.is_current,
                topic_count=topics,
                objective_count=objectives,
                source_file=spec.source_file,
            )
            for spec, subject_name, board_name, topics, objectives in rows
        ]

    # ------------------------------------------------------------ helpers

    async def _current_spec_id(
        self, subject_id: uuid.UUID, board_id: uuid.UUID
    ) -> uuid.UUID | None:
        return await self._session.scalar(
            select(Specification.id).where(
                Specification.subject_id == subject_id,
                Specification.board_id == board_id,
                Specification.is_current.is_(True),
            )
        )

    async def _drop_set_text_options(self, enrolment_id: uuid.UUID) -> None:
        """Set texts chosen from an old spec's list no longer apply; remove them."""
        await self._session.execute(
            delete(StudentSetText).where(
                StudentSetText.student_subject_id == enrolment_id,
                StudentSetText.set_text_option_id.is_not(None),
            )
        )

    async def _require_topic(self, enrolment: StudentSubject, topic_id: uuid.UUID) -> None:
        topic = await self._session.get(Topic, topic_id)
        if topic is None or topic.specification_id != enrolment.specification_id:
            raise NotFoundError("Topic not found")

    async def _subject_name(self, enrolment: StudentSubject) -> str:
        if enrolment.subject_id is None:
            return enrolment.custom_subject_name or ""
        subject = await self._session.get(Subject, enrolment.subject_id)
        return subject.name if subject else ""

    async def _admin_one(self, enrolment: StudentSubject) -> AdminEnrolmentOut:
        student = await self._session.get(User, enrolment.student_id)
        names = {student.id: student.display_name} if student else {}
        return (await self._describe([enrolment], names))[0]

    async def _describe(
        self, enrolments: Sequence[StudentSubject], student_names: dict[uuid.UUID, str]
    ) -> list[AdminEnrolmentOut]:
        """Build output models for many enrolments in 5 queries."""
        if not enrolments:
            return []
        subjects = await self._by_id(Subject, {e.subject_id for e in enrolments})
        boards = await self._by_id(ExamBoard, {e.board_id for e in enrolments})
        specs = await self._by_id(Specification, {e.specification_id for e in enrolments})
        texts = (
            await self._session.scalars(
                select(StudentSetText)
                .where(StudentSetText.student_subject_id.in_([e.id for e in enrolments]))
                .order_by(StudentSetText.position, StudentSetText.id)
            )
        ).all()
        options = await self._by_id(SetTextOption, {t.set_text_option_id for t in texts})
        texts_by_enrolment: dict[uuid.UUID, list[StudentSetTextOut]] = defaultdict(list)
        for text in texts:
            option = options.get(text.set_text_option_id) if text.set_text_option_id else None
            texts_by_enrolment[text.student_subject_id].append(
                StudentSetTextOut(
                    id=text.id,
                    category=text.category,
                    title=option.title if option else text.custom_title or "",
                    author=option.author if option else text.custom_author,
                    status=EnrolmentStatus.ACTIVE if option else EnrolmentStatus.PENDING,
                )
            )

        result = []
        for e in enrolments:
            subject = subjects.get(e.subject_id) if e.subject_id else None
            board = boards.get(e.board_id) if e.board_id else None
            spec = specs.get(e.specification_id) if e.specification_id else None
            set_texts = texts_by_enrolment[e.id]
            attention = []
            if spec is None:
                attention.append(AttentionReason.NO_SPECIFICATION)
            if not e.board_confirmed:
                attention.append(AttentionReason.BOARD_UNCONFIRMED)
            if not e.tier_confirmed:
                attention.append(AttentionReason.TIER_UNCONFIRMED)
            if any(t.status is EnrolmentStatus.PENDING for t in set_texts):
                attention.append(AttentionReason.SET_TEXT_PENDING)
            result.append(
                AdminEnrolmentOut(
                    id=e.id,
                    subject_id=e.subject_id,
                    subject_name=subject.name if subject else e.custom_subject_name or "",
                    is_custom=e.subject_id is None,
                    board_id=e.board_id,
                    board_name=board.name if board else None,
                    board_confirmed=e.board_confirmed,
                    tier=e.tier,
                    tier_confirmed=e.tier_confirmed,
                    status=EnrolmentStatus.ACTIVE if spec else EnrolmentStatus.PENDING,
                    specification=_spec_out(spec) if spec else None,
                    set_texts=set_texts,
                    student_id=e.student_id,
                    student_name=student_names.get(e.student_id, ""),
                    attention=attention,
                )
            )
        return result

    async def _by_id[M: (Subject, ExamBoard, Specification, SetTextOption)](
        self, model: type[M], ids: Iterable[uuid.UUID | None]
    ) -> dict[uuid.UUID, M]:
        wanted = {i for i in ids if i is not None}
        if not wanted:
            return {}
        rows = (await self._session.scalars(select(model).where(model.id.in_(wanted)))).all()
        return {row.id: row for row in rows}


def _enrolment_key(subject_id: uuid.UUID | None, custom_name: str | None) -> str:
    return str(subject_id) if subject_id else f"custom:{(custom_name or '').casefold()}"


def _reject_duplicates(choices: Sequence[SubjectChoice]) -> None:
    keys = [_enrolment_key(c.subject_id, c.custom_name) for c in choices]
    if len(keys) != len(set(keys)):
        raise InvalidRequestError("Each subject can only be chosen once")


def _resolve_board(choice: SubjectChoice, subject: Subject | None) -> tuple[uuid.UUID | None, bool]:
    """Return (board, confirmed). "I don't know" falls back to the most common board."""
    if choice.board_id is not None:
        return choice.board_id, True
    if subject is not None and subject.most_common_board_id is not None:
        return subject.most_common_board_id, False
    return None, False


def _resolve_tier(choice: SubjectChoice, subject: Subject | None) -> tuple[Tier | None, bool]:
    """Return (tier, confirmed). "Not sure" on a tiered subject falls back to Higher."""
    if subject is not None and not subject.has_tiers:
        if choice.tier is not None:
            raise InvalidRequestError(f"{subject.name} has no tiers")
        return None, True
    if choice.tier is not None:
        return choice.tier, True
    # Typed-in subjects: tiers are unknown until the admin matches a spec.
    return (Tier.HIGHER, False) if subject is not None else (None, False)
