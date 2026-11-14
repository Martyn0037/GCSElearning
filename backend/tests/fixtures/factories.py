# backend/tests/fixtures/factories.py
"""Test data factories and shared fake collaborators."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.core.config import Environment, Settings
from app.models.user import GuardianLink, Role, User

DEFAULT_PASSWORD = "correct-horse-battery"
FIXED_NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


@lru_cache(maxsize=1)
def default_password_hash() -> str:
    """Hash the default password once per test run (Argon2 is deliberately slow)."""
    return hash_password(DEFAULT_PASSWORD)


def make_settings(
    database_url: str = "postgresql+asyncpg://u:p@localhost/db", **overrides: object
) -> Settings:
    """Build settings for tests without reading any ``.env`` file."""
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "database_url": database_url,
        "jwt_secret": "test-jwt-secret-" + "x" * 32,
        "audit_ip_salt": "test-ip-salt-" + "y" * 32,
        "cors_origins": ["https://app.example.test"],
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@dataclass
class FakeClock:
    """A clock tests can move forward."""

    current: datetime = field(default_factory=lambda: FIXED_NOW)

    def now(self) -> datetime:
        """Return the fake current time."""
        return self.current

    def advance(self, **kwargs: float) -> None:
        """Move time forward by a ``timedelta(**kwargs)``."""
        self.current += timedelta(**kwargs)


async def create_user(
    session: AsyncSession,
    role: Role = Role.STUDENT,
    *,
    identifier: str | None = None,
    display_name: str = "Sam",
    is_active: bool = True,
) -> User:
    """Insert a user with the default password and commit.

    Args:
        session: Database session.
        role: Role for the user.
        identifier: Username (student) or email (others); random if omitted.
        display_name: First name / nickname.
        is_active: Whether the account can sign in.

    Returns:
        The committed user.
    """
    suffix = uuid.uuid4().hex[:8]
    if role is Role.STUDENT:
        username, email = (identifier or f"student{suffix}"), None
    else:
        username, email = None, (identifier or f"{role.value}{suffix}@example.test")
    user = User(
        role=role,
        username=username,
        email=email,
        display_name=display_name,
        password_hash=default_password_hash(),
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user


async def link(session: AsyncSession, guardian: User, student: User) -> None:
    """Link a guardian to a student and commit."""
    session.add(GuardianLink(guardian_id=guardian.id, student_id=student.id))
    await session.commit()


FIXTURE_CURRICULUM = Path(__file__).parent / "curriculum"


@dataclass(frozen=True)
class CurriculumIds:
    """IDs from the imported fixture curriculum, for building requests."""

    boards: dict[str, uuid.UUID]
    subjects: dict[str, uuid.UUID]
    specs: dict[str, uuid.UUID]
    topics: dict[str, uuid.UUID]
    set_texts: dict[str, uuid.UUID]


async def import_fixture_curriculum(session: AsyncSession) -> CurriculumIds:
    """Import ``tests/fixtures/curriculum`` and return the IDs tests need."""
    from sqlalchemy import select

    from app.cli.import_curriculum import load_folder
    from app.curriculum.importer import CurriculumImporter
    from app.models.curriculum import ExamBoard, SetTextOption, Specification, Subject, Topic

    catalogue, specs = load_folder(FIXTURE_CURRICULUM)
    importer = CurriculumImporter(session, FIXED_NOW)
    await importer.import_catalogue(catalogue, "catalogue.yaml")
    for source, spec in specs:
        await importer.import_specification(spec, source)
    await session.commit()

    boards = {b.code: b.id for b in (await session.scalars(select(ExamBoard))).all()}
    subjects = {s.slug: s.id for s in (await session.scalars(select(Subject))).all()}
    spec_ids = {s.code: s.id for s in (await session.scalars(select(Specification))).all()}
    topics = {
        f"{code}:{t.ref}": t.id
        for code, spec_id in spec_ids.items()
        for t in (
            await session.scalars(select(Topic).where(Topic.specification_id == spec_id))
        ).all()
    }
    set_texts = {o.title: o.id for o in (await session.scalars(select(SetTextOption))).all()}
    return CurriculumIds(boards, subjects, spec_ids, topics, set_texts)


async def create_question(
    session: AsyncSession,
    objective_id: uuid.UUID,
    *,
    difficulty: int = 1,
    tier: object = None,
    question_type: str = "multiple_choice",
    status: str = "active",
    stem: str | None = None,
) -> uuid.UUID:
    """Insert a bank question with four hints and commit; returns its ID."""
    from app.models.curriculum import Tier
    from app.models.question import Hint, Question, QuestionStatus, QuestionType

    qtype = QuestionType(question_type)
    keys: dict[QuestionType, dict[str, object]] = {
        QuestionType.MULTIPLE_CHOICE: {"correct_option": "C"},
        QuestionType.NUMERIC: {"value": "4.75", "tolerance": "0", "unit": "cm"},
        QuestionType.SHORT_TEXT: {"accepted": ["prime", "prime number"]},
    }
    answer = keys[qtype]
    question = Question(
        id=uuid.uuid4(),
        objective_id=objective_id,
        tier=Tier(tier) if isinstance(tier, str) else tier,
        difficulty=difficulty,
        question_type=qtype,
        command_word="Work out",
        stem=stem or f"Question {uuid.uuid4().hex[:6]}",
        options=[
            {"label": x, "text": t} for x, t in zip("ABCD", ["2", "3", "6", "36"], strict=True)
        ]
        if qtype is QuestionType.MULTIPLE_CHOICE
        else None,
        answer=answer,
        marks=1,
        worked_solution="The worked solution.",
        status=QuestionStatus(status),
        verified=True,
        confidence=0.95,
        generator_model="test",
        content_hash=uuid.uuid4().hex,
    )
    session.add(question)
    await session.flush()
    session.add_all(Hint(question_id=question.id, level=i, text=f"Hint {i}") for i in range(1, 5))
    await session.commit()
    return question.id
