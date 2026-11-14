# backend/app/cli/import_curriculum.py
"""Import curriculum YAML (catalogue first, then every spec file).

Usage::

    python -m app.cli.import_curriculum /app/curriculum            # whole folder
    python -m app.cli.import_curriculum --check /app/curriculum    # validate only

The folder must contain ``catalogue.yaml`` and may contain ``specs/*.yaml``.
Every file is validated before anything is written; if any file is invalid,
nothing is imported. Safe to run repeatedly (it runs on every deploy).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.curriculum.importer import (
    CurriculumFileError,
    CurriculumImporter,
    ImportReport,
    parse_catalogue,
    parse_specification,
    read_yaml,
)
from app.curriculum.schema import CatalogueFile, SpecificationFile
from app.db.session import create_engine, create_session_factory


def load_folder(folder: Path) -> tuple[CatalogueFile, list[tuple[str, SpecificationFile]]]:
    """Read and validate every curriculum file in ``folder``.

    Returns:
        The catalogue and each spec with its path relative to ``folder``.

    Raises:
        CurriculumFileError: Listing the problems in every invalid file.
    """
    catalogue_path = folder / "catalogue.yaml"
    if not catalogue_path.is_file():
        raise CurriculumFileError(f"{catalogue_path} not found")
    problems: list[str] = []
    catalogue: CatalogueFile | None = None
    try:
        catalogue = parse_catalogue(read_yaml(catalogue_path), "catalogue.yaml")
    except CurriculumFileError as exc:
        problems.append(str(exc))
    specs: list[tuple[str, SpecificationFile]] = []
    for path in sorted((folder / "specs").glob("*.yaml")):
        source = str(path.relative_to(folder))
        try:
            specs.append((source, parse_specification(read_yaml(path), source)))
        except CurriculumFileError as exc:
            problems.append(str(exc))
    if problems or catalogue is None:
        raise CurriculumFileError("\n".join(problems))
    return catalogue, specs


async def import_folder(folder: Path) -> list[ImportReport]:
    """Validate everything, then import it in one transaction."""
    catalogue, specs = load_folder(folder)
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            importer = CurriculumImporter(session, SystemClock().now())
            reports = [await importer.import_catalogue(catalogue, "catalogue.yaml")]
            for source, spec in specs:
                reports.append(await importer.import_specification(spec, source))
            await session.commit()
            return reports
    finally:
        await engine.dispose()


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Import curriculum YAML files")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args()
    try:
        if args.check:
            _, specs = load_folder(args.folder)
            print(f"OK: catalogue.yaml and {len(specs)} spec file(s) are valid.")
            return
        for report in asyncio.run(import_folder(args.folder)):
            print(report.summary())
    except CurriculumFileError as exc:
        sys.exit(f"Curriculum import failed; nothing was changed.\n{exc}")


if __name__ == "__main__":
    main()
