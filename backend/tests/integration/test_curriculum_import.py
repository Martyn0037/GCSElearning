# backend/tests/integration/test_curriculum_import.py
"""Integration tests for importing curriculum into PostgreSQL.

Covers:
- first import creates everything; re-import changes nothing (idempotent)
- changed wording updates in place; removed statements are retired, not deleted;
  re-adding un-retires
- a new current version takes over is_current from the old one
- unknown board/subject -> error
- importing a spec activates matching pending enrolments (and ones on a board
  with no spec for the subject, unless their board has its own) and matches
  typed-in set texts by exact title (case/apostrophe-insensitive)
- the real repo curriculum imports cleanly
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.import_curriculum import load_folder
from app.curriculum.importer import CurriculumFileError, CurriculumImporter, read_yaml
from app.curriculum.schema import SpecificationFile
from app.models.curriculum import ExamBoard, LearningObjective, Specification, Subject
from app.models.enrolment import StudentSetText, StudentSubject
from app.models.user import Role
from tests.fixtures.factories import (
    FIXED_NOW,
    FIXTURE_CURRICULUM,
    create_user,
    import_fixture_curriculum,
)
from tests.unit.test_curriculum_schema import REPO_CURRICULUM

pytestmark = pytest.mark.integration


def _maths_spec_data() -> dict[str, Any]:
    data = read_yaml(FIXTURE_CURRICULUM / "specs" / "board-a-m1.yaml")
    assert isinstance(data, dict)
    return copy.deepcopy(data)


async def _import(session: AsyncSession, data: dict[str, Any]) -> Any:
    report = await CurriculumImporter(session, FIXED_NOW).import_specification(
        SpecificationFile.model_validate(data), "specs/board-a-m1.yaml"
    )
    await session.commit()
    return report


async def test_should_create_everything_then_change_nothing_on_reimport(
    session: AsyncSession,
) -> None:
    # Arrange / Act
    await import_fixture_curriculum(session)
    again = await _import(session, _maths_spec_data())

    # Assert
    objectives = await session.scalar(select(func.count()).select_from(LearningObjective))
    assert objectives == 6  # M1: 4, L1: 1, L2: 1
    assert (again.created, again.updated, again.retired) == (0, 0, 0)


async def test_should_update_changed_wording_in_place(session: AsyncSession) -> None:
    ids = await import_fixture_curriculum(session)
    data = _maths_spec_data()
    data["topics"][0]["subtopics"][0]["objectives"][0]["foundation"] = "order integers carefully"

    report = await _import(session, data)

    row = await session.scalar(
        select(LearningObjective).where(
            LearningObjective.specification_id == ids.specs["M1"], LearningObjective.ref == "T1"
        )
    )
    assert report.updated == 1
    assert row is not None
    assert row.foundation_text == "order integers carefully"


async def test_should_retire_removed_statements_and_restore_them_when_readded(
    session: AsyncSession,
) -> None:
    await import_fixture_curriculum(session)
    original = _maths_spec_data()
    trimmed = copy.deepcopy(original)
    trimmed["topics"][0]["subtopics"][0]["objectives"].pop()  # drop T3

    removed = await _import(session, trimmed)
    t3 = await session.scalar(select(LearningObjective).where(LearningObjective.ref == "T3"))
    assert removed.retired == 1
    assert t3 is not None
    assert t3.retired_at is not None

    await _import(session, original)
    await session.refresh(t3)
    assert t3.retired_at is None


async def test_new_current_version_should_replace_old_as_current(session: AsyncSession) -> None:
    ids = await import_fixture_curriculum(session)
    data = _maths_spec_data()
    data["specification"]["version"] = "Issue 2"

    await _import(session, data)

    old = await session.get(Specification, ids.specs["M1"])
    current = (
        await session.scalars(
            select(Specification).where(
                Specification.is_current.is_(True), Specification.code == "M1"
            )
        )
    ).all()
    assert old is not None
    await session.refresh(old)
    assert old.is_current is False
    assert [s.version for s in current] == ["Issue 2"]


async def test_should_reject_spec_for_unknown_board(session: AsyncSession) -> None:
    await import_fixture_curriculum(session)
    data = _maths_spec_data()
    data["specification"]["board"] = "board-z"

    with pytest.raises(CurriculumFileError, match=r"board 'board-z' isn't in catalogue\.yaml"):
        await _import(session, data)


async def test_import_should_activate_pending_enrolments_and_match_typed_set_texts(
    session: AsyncSession,
) -> None:
    # Arrange: the catalogue exists but the English spec doesn't yet; the
    # student has chosen it and typed a set text.
    catalogue, specs = load_folder(FIXTURE_CURRICULUM)
    importer = CurriculumImporter(session, FIXED_NOW)
    await importer.import_catalogue(catalogue, "catalogue.yaml")
    await session.commit()
    student = await create_user(session, Role.STUDENT)
    board = await session.scalar(select(ExamBoard).where(ExamBoard.code == "board-b"))
    subject = await session.scalar(select(Subject).where(Subject.slug == "english-literature"))
    assert board is not None
    assert subject is not None
    enrolment = StudentSubject(
        id=uuid.uuid4(),
        student_id=student.id,
        subject_id=subject.id,
        board_id=board.id,
        board_confirmed=True,
        tier=None,
        tier_confirmed=True,
        position=0,
    )
    session.add(enrolment)
    await session.flush()
    session.add_all(
        [
            StudentSetText(
                student_subject_id=enrolment.id,
                category="Shakespeare play",
                custom_title="  macbeth ",
                position=0,
            ),
            StudentSetText(
                student_subject_id=enrolment.id,
                category="Shakespeare play",
                custom_title="Hamlet",
                position=1,
            ),
        ]
    )
    await session.commit()

    # Act
    english = next(spec for source, spec in specs if "l1" in source)
    report = await importer.import_specification(english, "specs/board-b-l1.yaml")
    await session.commit()

    # Assert
    await session.refresh(enrolment)
    texts = {
        (t.custom_title or "").strip(): t.set_text_option_id is not None
        for t in (await session.scalars(select(StudentSetText))).all()
    }
    assert report.enrolments_activated == 1
    assert enrolment.specification_id is not None
    assert report.set_texts_matched == 1
    assert texts == {"macbeth": True, "Hamlet": False}


async def _pending(session: AsyncSession, subject_slug: str, board_code: str) -> StudentSubject:
    student = await create_user(session, Role.STUDENT)
    board = await session.scalar(select(ExamBoard).where(ExamBoard.code == board_code))
    subject = await session.scalar(select(Subject).where(Subject.slug == subject_slug))
    assert board is not None
    assert subject is not None
    enrolment = StudentSubject(
        student_id=student.id,
        subject_id=subject.id,
        board_id=board.id,
        board_confirmed=True,
        tier=None,
        tier_confirmed=True,
        position=0,
    )
    session.add(enrolment)
    await session.commit()
    return enrolment


async def test_import_should_move_a_pending_enrolment_on_a_board_without_a_spec(
    session: AsyncSession,
) -> None:
    # Arrange: maths chosen on board B, which has no maths spec
    catalogue, specs = load_folder(FIXTURE_CURRICULUM)
    importer = CurriculumImporter(session, FIXED_NOW)
    await importer.import_catalogue(catalogue, "catalogue.yaml")
    await session.commit()
    enrolment = await _pending(session, "maths", "board-b")

    # Act
    maths = next(spec for source, spec in specs if "m1" in source)
    report = await importer.import_specification(maths, "specs/board-a-m1.yaml")
    await session.commit()

    # Assert
    await session.refresh(enrolment)
    board_a = await session.scalar(select(ExamBoard.id).where(ExamBoard.code == "board-a"))
    assert report.enrolments_activated == 1
    assert enrolment.specification_id is not None
    assert enrolment.board_id == board_a


async def test_import_should_not_take_an_enrolment_whose_board_has_its_own_spec(
    session: AsyncSession,
) -> None:
    # Arrange: board A's English spec is imported, then a pending board-A enrolment exists
    catalogue, specs = load_folder(FIXTURE_CURRICULUM)
    importer = CurriculumImporter(session, FIXED_NOW)
    await importer.import_catalogue(catalogue, "catalogue.yaml")
    board_a_spec = next(spec for source, spec in specs if "l2" in source)
    await importer.import_specification(board_a_spec, "specs/board-a-l2.yaml")
    await session.commit()
    enrolment = await _pending(session, "english-literature", "board-a")

    # Act: board B's English spec is imported
    board_b_spec = next(spec for source, spec in specs if "l1" in source)
    report = await importer.import_specification(board_b_spec, "specs/board-b-l1.yaml")
    await session.commit()

    # Assert: left for its own board's spec
    await session.refresh(enrolment)
    assert report.enrolments_activated == 0
    assert enrolment.specification_id is None


async def test_repo_curriculum_should_import(session: AsyncSession) -> None:
    catalogue, specs = load_folder(REPO_CURRICULUM)
    importer = CurriculumImporter(session, FIXED_NOW)
    await importer.import_catalogue(catalogue, "catalogue.yaml")
    reports = [await importer.import_specification(spec, source) for source, spec in specs]
    await session.commit()

    n16 = await session.scalar(select(LearningObjective).where(LearningObjective.ref == "N16"))
    assert all(r.created > 0 for r in reports)
    assert n16 is not None
    assert (
        n16.higher_text
        == "apply and interpret limits of accuracy, including upper and lower bounds"
    )
