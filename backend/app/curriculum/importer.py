# backend/app/curriculum/importer.py
"""Load curriculum YAML into the database.

Imports are idempotent: running the same file twice changes nothing.
Statements removed from a file are *retired* (hidden), never deleted, because
attempts and mistakes will reference them. Importing a spec also activates any
pending student subjects it matches (ADR-012).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.curriculum.schema import CatalogueFile, SpecificationFile
from app.models.curriculum import (
    ExamBoard,
    LearningObjective,
    SetTextOption,
    Specification,
    Subject,
    Subtopic,
    Topic,
)
from app.models.enrolment import StudentSetText, StudentSubject

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 2 * 1024 * 1024


class CurriculumFileError(Exception):
    """A curriculum file couldn't be read or failed validation."""


@dataclass
class ImportReport:
    """What an import changed."""

    source: str
    created: int = 0
    updated: int = 0
    retired: int = 0
    enrolments_activated: int = 0
    set_texts_matched: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One line for the command output."""
        return (
            f"{self.source}: {self.created} created, {self.updated} updated, "
            f"{self.retired} retired, {self.enrolments_activated} subject(s) activated, "
            f"{self.set_texts_matched} set text(s) matched"
        )


def read_yaml(path: Path) -> Any:
    """Read a YAML file safely (no arbitrary object construction).

    Raises:
        CurriculumFileError: If the file is too large or isn't valid YAML.
    """
    if path.stat().st_size > MAX_FILE_BYTES:
        raise CurriculumFileError(f"{path}: larger than {MAX_FILE_BYTES} bytes")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CurriculumFileError(f"{path}: invalid YAML: {exc}") from exc


def parse_catalogue(data: Any, source: str) -> CatalogueFile:
    """Validate catalogue data.

    Raises:
        CurriculumFileError: With every validation problem listed.
    """
    try:
        return CatalogueFile.model_validate(data)
    except ValidationError as exc:
        raise CurriculumFileError(_describe(source, exc)) from exc


def parse_specification(data: Any, source: str) -> SpecificationFile:
    """Validate specification data.

    Raises:
        CurriculumFileError: With every validation problem listed.
    """
    try:
        return SpecificationFile.model_validate(data)
    except ValidationError as exc:
        raise CurriculumFileError(_describe(source, exc)) from exc


def _describe(source: str, exc: ValidationError) -> str:
    lines = [f"{source}: {exc.error_count()} problem(s)"]
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(file)"
        lines.append(f"  - {where}: {err['msg']}")
    return "\n".join(lines)


def _set(row: object, changes: dict[str, object]) -> bool:
    """Apply changed attributes to ``row``; return whether anything changed."""
    changed = False
    for name, value in changes.items():
        if getattr(row, name) != value:
            setattr(row, name, value)
            changed = True
    return changed


class CurriculumImporter:
    """Writes validated curriculum files into the database (caller commits)."""

    def __init__(self, session: AsyncSession, now: datetime) -> None:
        """Create an importer.

        Args:
            session: Database session; the caller commits or rolls back.
            now: Timestamp used when retiring rows.
        """
        self._session = session
        self._now = now

    async def import_catalogue(self, catalogue: CatalogueFile, source: str) -> ImportReport:
        """Create or update boards and subjects. Nothing is deleted."""
        report = ImportReport(source)
        boards = {b.code: b for b in (await self._session.scalars(select(ExamBoard))).all()}
        for position, entry in enumerate(catalogue.boards):
            board = boards.get(entry.code)
            if board is None:
                board = ExamBoard(
                    id=uuid.uuid4(), code=entry.code, name=entry.name, position=position
                )
                self._session.add(board)
                boards[entry.code] = board
                report.created += 1
            elif _set(board, {"name": entry.name, "position": position}):
                report.updated += 1
        await self._session.flush()

        subjects = {s.slug: s for s in (await self._session.scalars(select(Subject))).all()}
        for position, item in enumerate(catalogue.subjects):
            values: dict[str, object] = {
                "name": item.name,
                "has_tiers": item.has_tiers,
                "set_text_categories": list(item.set_text_categories),
                "most_common_board_id": boards[item.most_common_board].id
                if item.most_common_board
                else None,
                "position": position,
            }
            subject = subjects.get(item.slug)
            if subject is None:
                self._session.add(Subject(id=uuid.uuid4(), slug=item.slug, **values))
                report.created += 1
            elif _set(subject, values):
                report.updated += 1
        await self._session.flush()
        return report

    async def import_specification(self, spec_file: SpecificationFile, source: str) -> ImportReport:
        """Create or update one specification version and all its content.

        Raises:
            CurriculumFileError: If the board or subject isn't in the catalogue.
        """
        report = ImportReport(source)
        header = spec_file.specification
        board = await self._session.scalar(select(ExamBoard).where(ExamBoard.code == header.board))
        subject = await self._session.scalar(select(Subject).where(Subject.slug == header.subject))
        if board is None or subject is None:
            missing = "board" if board is None else "subject"
            raise CurriculumFileError(
                f"{source}: {missing} {getattr(header, missing)!r} isn't in catalogue.yaml; "
                "import the catalogue first"
            )

        spec = await self._session.scalar(
            select(Specification).where(
                Specification.board_id == board.id,
                Specification.code == header.code,
                Specification.version == header.version,
            )
        )
        if header.current:
            # Only one current version per board + code (partial unique index).
            await self._session.execute(
                update(Specification)
                .where(
                    Specification.board_id == board.id,
                    Specification.code == header.code,
                    Specification.version != header.version,
                    Specification.is_current.is_(True),
                )
                .values(is_current=False)
            )
        spec_values: dict[str, object] = {
            "subject_id": subject.id,
            "title": header.title,
            "source_url": str(header.source_url) if header.source_url else None,
            "tiered": header.tiered,
            "is_current": header.current,
            "source_file": source,
        }
        if spec is None:
            spec = Specification(
                id=uuid.uuid4(),
                board_id=board.id,
                code=header.code,
                version=header.version,
                **spec_values,
            )
            self._session.add(spec)
            report.created += 1
        elif _set(spec, spec_values):
            report.updated += 1
        await self._session.flush()

        await self._import_content(spec, spec_file, report)
        await self._import_set_texts(spec, spec_file, report)
        await self._session.flush()
        if spec.is_current:
            report.enrolments_activated = await self._activate_pending(spec)
        report.set_texts_matched = await self._match_custom_set_texts(spec)
        return report

    async def _import_content(
        self, spec: Specification, spec_file: SpecificationFile, report: ImportReport
    ) -> None:
        topics = {
            t.ref: t
            for t in (
                await self._session.scalars(select(Topic).where(Topic.specification_id == spec.id))
            ).all()
        }
        topic_ids = [t.id for t in topics.values()]
        subtopics = {
            (s.topic_id, s.title): s
            for s in (
                await self._session.scalars(
                    select(Subtopic).where(Subtopic.topic_id.in_(topic_ids))
                )
            ).all()
        }
        objectives = {
            o.ref: o
            for o in (
                await self._session.scalars(
                    select(LearningObjective).where(LearningObjective.specification_id == spec.id)
                )
            ).all()
        }
        seen_topics: set[uuid.UUID] = set()
        seen_subtopics: set[uuid.UUID] = set()
        seen_objectives: set[uuid.UUID] = set()

        for t_pos, t_entry in enumerate(spec_file.topics):
            topic = topics.get(t_entry.ref)
            t_values: dict[str, object] = {
                "title": t_entry.title,
                "position": t_pos,
                "retired_at": None,
            }
            if topic is None:
                topic = Topic(
                    id=uuid.uuid4(), specification_id=spec.id, ref=t_entry.ref, **t_values
                )
                self._session.add(topic)
                # No ORM relationships are declared, so flush parents before
                # adding children to keep foreign keys satisfied.
                await self._session.flush()
                report.created += 1
            elif _set(topic, t_values):
                report.updated += 1
            seen_topics.add(topic.id)

            for s_pos, s_entry in enumerate(t_entry.subtopics):
                subtopic = subtopics.get((topic.id, s_entry.title))
                s_values: dict[str, object] = {"position": s_pos, "retired_at": None}
                if subtopic is None:
                    subtopic = Subtopic(
                        id=uuid.uuid4(), topic_id=topic.id, title=s_entry.title, **s_values
                    )
                    self._session.add(subtopic)
                    await self._session.flush()
                    report.created += 1
                elif _set(subtopic, s_values):
                    report.updated += 1
                seen_subtopics.add(subtopic.id)

                for o_pos, o_entry in enumerate(s_entry.objectives):
                    objective = objectives.get(o_entry.ref)
                    o_values: dict[str, object] = {
                        "subtopic_id": subtopic.id,
                        "foundation_text": o_entry.foundation,
                        "higher_text": o_entry.higher,
                        "keywords": list(o_entry.keywords),
                        "out_of_scope": o_entry.out_of_scope,
                        "position": o_pos,
                        "retired_at": None,
                    }
                    if objective is None:
                        objective = LearningObjective(
                            id=uuid.uuid4(), specification_id=spec.id, ref=o_entry.ref, **o_values
                        )
                        self._session.add(objective)
                        report.created += 1
                    elif _set(objective, o_values):
                        report.updated += 1
                    seen_objectives.add(objective.id)
                await self._session.flush()

        report.retired += self._retire(topics.values(), seen_topics)
        report.retired += self._retire(subtopics.values(), seen_subtopics)
        report.retired += self._retire(objectives.values(), seen_objectives)

    async def _import_set_texts(
        self, spec: Specification, spec_file: SpecificationFile, report: ImportReport
    ) -> None:
        existing = {
            (o.category, o.title): o
            for o in (
                await self._session.scalars(
                    select(SetTextOption).where(SetTextOption.specification_id == spec.id)
                )
            ).all()
        }
        seen: set[uuid.UUID] = set()
        position = 0
        for group in spec_file.set_texts:
            for entry in group.options:
                option = existing.get((group.category, entry.title))
                values: dict[str, object] = {
                    "author": entry.author,
                    "position": position,
                    "retired_at": None,
                }
                if option is None:
                    option = SetTextOption(
                        id=uuid.uuid4(),
                        specification_id=spec.id,
                        category=group.category,
                        title=entry.title,
                        **values,
                    )
                    self._session.add(option)
                    report.created += 1
                elif _set(option, values):
                    report.updated += 1
                seen.add(option.id)
                position += 1
        report.retired += self._retire(existing.values(), seen)

    def _retire(self, rows: Any, keep: set[uuid.UUID]) -> int:
        count = 0
        for row in rows:
            if row.id not in keep and row.retired_at is None:
                row.retired_at = self._now
                count += 1
        return count

    async def _activate_pending(self, spec: Specification) -> int:
        """Link pending enrolments for this subject to the spec.

        Enrolments on this spec's board are linked. So are ones on a board
        with no current spec for the subject, which move to this spec's board
        (everything is usable straight away, ADR-021).
        """
        board_has_own_spec = (
            select(Specification.id)
            .where(
                Specification.subject_id == spec.subject_id,
                Specification.board_id == StudentSubject.board_id,
                Specification.is_current.is_(True),
            )
            .exists()
        )
        result = await self._session.execute(
            update(StudentSubject)
            .where(
                StudentSubject.specification_id.is_(None),
                StudentSubject.subject_id == spec.subject_id,
                or_(StudentSubject.board_id == spec.board_id, ~board_has_own_spec),
            )
            .values(specification_id=spec.id, board_id=spec.board_id)
            .execution_options(synchronize_session=False)
        )
        count = int(result.rowcount)  # type: ignore[attr-defined]
        if count:
            logger.info("enrolments_activated", extra={"count": count, "spec": spec.code})
        return count

    async def _match_custom_set_texts(self, spec: Specification) -> int:
        """Match typed-in set texts to this spec's options by exact title."""
        options = (
            await self._session.scalars(
                select(SetTextOption).where(
                    SetTextOption.specification_id == spec.id, SetTextOption.retired_at.is_(None)
                )
            )
        ).all()
        by_key = {(o.category, _key(o.title)): o for o in options}
        pending = (
            await self._session.scalars(
                select(StudentSetText)
                .join(StudentSubject, StudentSubject.id == StudentSetText.student_subject_id)
                .where(
                    StudentSubject.specification_id == spec.id,
                    StudentSetText.set_text_option_id.is_(None),
                )
            )
        ).all()
        matched = 0
        for item in pending:
            option = by_key.get((item.category, _key(item.custom_title or "")))
            if option is not None:
                item.set_text_option_id = option.id
                matched += 1
        return matched


def _key(title: str) -> str:
    return " ".join(title.lower().replace("\u2019", "'").split())
