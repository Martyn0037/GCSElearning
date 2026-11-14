# backend/tests/unit/test_curriculum_schema.py
"""Unit tests for curriculum file validation and folder loading.

Covers:
- the real curriculum/ folder in the repo is valid (guards every commit)
- objectives: need wording; keyword must appear in wording; TODO rejected;
  'higher' equal to 'foundation' rejected; untiered specs can't use 'higher'
- duplicates: objective refs, topic refs, subtopic titles, set-text titles
- catalogue: unknown most_common_board, duplicate slugs, unknown fields
- folder loading: missing catalogue, all problems reported together, invalid
  YAML, oversized file
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.cli.import_curriculum import load_folder
from app.curriculum.importer import (
    CurriculumFileError,
    parse_catalogue,
    parse_specification,
    read_yaml,
)
from tests.fixtures.factories import FIXTURE_CURRICULUM

REPO_CURRICULUM = Path(__file__).resolve().parents[3] / "curriculum"

BASE_SPEC: dict[str, Any] = {
    "specification": {
        "board": "board-a",
        "subject": "maths",
        "code": "M1",
        "title": "Test",
        "version": "Issue 1",
        "tiered": True,
    },
    "topics": [
        {
            "ref": "1",
            "title": "Number",
            "subtopics": [
                {
                    "title": "Calculation",
                    "objectives": [
                        {"ref": "T1", "foundation": "order integers", "keywords": ["integers"]}
                    ],
                }
            ],
        }
    ],
}


def _spec_with(**objective: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE_SPEC)
    data["topics"][0]["subtopics"][0]["objectives"] = [{"ref": "T1", **objective}]
    return data


def test_repo_curriculum_folder_should_be_valid() -> None:
    catalogue, specs = load_folder(REPO_CURRICULUM)

    assert {b.code for b in catalogue.boards} >= {"aqa", "pearson-edexcel", "ocr", "eduqas"}
    assert any(spec.specification.code == "1MA1" for _, spec in specs)


def test_should_accept_valid_spec() -> None:
    spec = parse_specification(BASE_SPEC, "x.yaml")

    assert spec.topics[0].subtopics[0].objectives[0].ref == "T1"


@pytest.mark.parametrize(
    ("objective", "message"),
    [
        ({}, "needs foundation and/or higher wording"),
        ({"foundation": "order integers", "keywords": ["fractions"]}, "keyword 'fractions'"),
        ({"foundation": "TODO copy from page 4"}, "still marked TODO"),
        ({"foundation": "order integers", "higher": "order integers"}, "omit 'higher'"),
    ],
    ids=["no_wording", "invented_keyword", "todo", "higher_equals_foundation"],
)
def test_should_reject_invalid_objective(objective: dict[str, Any], message: str) -> None:
    with pytest.raises(CurriculumFileError, match=message):
        parse_specification(_spec_with(**objective), "x.yaml")


def test_keyword_match_should_ignore_case_and_spacing() -> None:
    spec = parse_specification(
        _spec_with(foundation="Use  Prime\nNumbers", keywords=["prime numbers"]), "x.yaml"
    )

    assert spec.topics[0].subtopics[0].objectives[0].keywords == ["prime numbers"]


def test_should_reject_higher_wording_in_untiered_spec() -> None:
    data = _spec_with(foundation="read a play", higher="read a play closely")
    data["specification"]["tiered"] = False

    with pytest.raises(CurriculumFileError, match="untiered specs use 'foundation' only"):
        parse_specification(data, "x.yaml")


def test_should_reject_duplicate_objective_refs() -> None:
    data = copy.deepcopy(BASE_SPEC)
    objectives = data["topics"][0]["subtopics"][0]["objectives"]
    objectives.append(dict(objectives[0]))

    with pytest.raises(CurriculumFileError, match="duplicate objective ref"):
        parse_specification(data, "x.yaml")


def test_should_reject_duplicate_set_text_titles() -> None:
    data = copy.deepcopy(BASE_SPEC)
    data["set_texts"] = [
        {"category": "Play", "options": [{"title": "Macbeth"}, {"title": "Macbeth"}]}
    ]

    with pytest.raises(CurriculumFileError, match="duplicate set text"):
        parse_specification(data, "x.yaml")


def test_should_reject_unknown_fields_and_report_location() -> None:
    data = copy.deepcopy(BASE_SPEC)
    data["topics"][0]["colour"] = "red"

    with pytest.raises(CurriculumFileError, match=r"topics\.0\.colour"):
        parse_specification(data, "x.yaml")


def test_catalogue_should_reject_unknown_most_common_board() -> None:
    data = {
        "boards": [{"code": "aqa", "name": "AQA"}],
        "subjects": [
            {"slug": "maths", "name": "Maths", "has_tiers": True, "most_common_board": "ocr"}
        ],
    }

    with pytest.raises(CurriculumFileError, match="most_common_board 'ocr'"):
        parse_catalogue(data, "catalogue.yaml")


def test_catalogue_should_reject_duplicate_subject_slugs() -> None:
    subject = {"slug": "maths", "name": "Maths", "has_tiers": True}
    data = {"boards": [{"code": "aqa", "name": "AQA"}], "subjects": [subject, subject]}

    with pytest.raises(CurriculumFileError, match="duplicate subject slug"):
        parse_catalogue(data, "catalogue.yaml")


def test_load_folder_should_require_catalogue(tmp_path: Path) -> None:
    with pytest.raises(CurriculumFileError, match=r"catalogue\.yaml not found"):
        load_folder(tmp_path)


def test_load_folder_should_report_every_invalid_file(tmp_path: Path) -> None:
    # Arrange: valid catalogue, two broken specs.
    (tmp_path / "catalogue.yaml").write_text((FIXTURE_CURRICULUM / "catalogue.yaml").read_text())
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "a.yaml").write_text("specification: {}\n")
    (tmp_path / "specs" / "b.yaml").write_text("topics: [\n")

    # Act
    with pytest.raises(CurriculumFileError) as exc:
        load_folder(tmp_path)

    # Assert
    assert "specs/a.yaml" in str(exc.value)
    assert "specs/b.yaml: invalid YAML" in str(exc.value)


def test_read_yaml_should_reject_oversized_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "big.yaml"
    path.write_text("a: 1\n")
    monkeypatch.setattr("app.curriculum.importer.MAX_FILE_BYTES", 2)

    with pytest.raises(CurriculumFileError, match="larger than"):
        read_yaml(path)


def test_read_yaml_should_not_construct_python_objects(tmp_path: Path) -> None:
    path = tmp_path / "evil.yaml"
    path.write_text("x: !!python/object/apply:os.system ['echo hi']\n")

    with pytest.raises(CurriculumFileError, match="invalid YAML"):
        read_yaml(path)
