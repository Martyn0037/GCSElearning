# backend/app/curriculum/schema.py
"""The YAML file formats for curriculum data, validated with Pydantic.

Two kinds of file live under ``curriculum/``:

- ``catalogue.yaml``: exam boards and the subjects the student can choose.
- ``specs/*.yaml``: one exact version of one board's specification.

The rules here enforce ADR-012 (nothing invented): every objective needs its
spec reference and exact wording, and every keyword must appear word for word
in that wording.
"""

from __future__ import annotations

import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Wording = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=4000)]

# A spec statement still to be copied from the PDF. Files containing it are
# rejected so half-finished content never reaches the student.
TODO_MARKER = re.compile(r"\bTODO\b")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BoardEntry(_Strict):
    """An exam board."""

    code: Slug
    name: ShortText


class SubjectEntry(_Strict):
    """A subject the student can pick on the setup screen."""

    slug: Slug
    name: ShortText
    has_tiers: bool
    most_common_board: Slug | None = Field(
        default=None, description="Pre-selected board; the student can change it"
    )
    set_text_categories: list[ShortText] = Field(default_factory=list)


class CatalogueFile(_Strict):
    """``curriculum/catalogue.yaml``."""

    boards: list[BoardEntry] = Field(min_length=1)
    subjects: list[SubjectEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        board_codes = [b.code for b in self.boards]
        _require_unique("board code", board_codes)
        _require_unique("subject slug", [s.slug for s in self.subjects])
        for subject in self.subjects:
            if subject.most_common_board and subject.most_common_board not in board_codes:
                raise ValueError(
                    f"subject {subject.slug!r}: most_common_board "
                    f"{subject.most_common_board!r} isn't in boards"
                )
        return self


class ObjectiveEntry(_Strict):
    """One spec statement."""

    ref: ShortText
    foundation: Wording | None = Field(
        default=None,
        description="Foundation wording (or the only wording, for untiered specs). "
        "Omit for Higher-only statements.",
    )
    higher: Wording | None = Field(
        default=None, description="Higher wording, only when it differs from Foundation"
    )
    keywords: list[ShortText] = Field(default_factory=list)
    out_of_scope: Wording | None = None

    @model_validator(mode="after")
    def _check_wording(self) -> Self:
        if self.foundation is None and self.higher is None:
            raise ValueError(f"objective {self.ref}: needs foundation and/or higher wording")
        if self.higher is not None and self.higher == self.foundation:
            raise ValueError(f"objective {self.ref}: omit 'higher' when it equals 'foundation'")
        all_text = " ".join(t for t in (self.foundation, self.higher) if t)
        if TODO_MARKER.search(all_text):
            raise ValueError(f"objective {self.ref}: still marked TODO")
        lowered = _normalise(all_text)
        for keyword in self.keywords:
            if _normalise(keyword) not in lowered:
                raise ValueError(
                    f"objective {self.ref}: keyword {keyword!r} isn't in its wording "
                    "(keywords must be copied from the spec text)"
                )
        return self


class SubtopicEntry(_Strict):
    """A heading inside a topic."""

    title: ShortText
    objectives: list[ObjectiveEntry] = Field(min_length=1)


class TopicEntry(_Strict):
    """A top-level spec section."""

    ref: ShortText
    title: ShortText
    subtopics: list[SubtopicEntry] = Field(min_length=1)


class SetTextEntry(_Strict):
    """A set text the board allows."""

    title: ShortText
    author: ShortText | None = None


class SetTextGroup(_Strict):
    """The allowed texts in one category, e.g. "Shakespeare play"."""

    category: ShortText
    options: list[SetTextEntry] = Field(min_length=1)


class SpecificationHeader(_Strict):
    """Identifies exactly which document the content was copied from."""

    board: Slug
    subject: Slug
    code: ShortText
    title: ShortText
    version: ShortText = Field(description="Exactly as printed in the PDF footer")
    source_url: HttpUrl | None = None
    tiered: bool
    current: bool = Field(
        default=True, description="Use this version for new and pending enrolments"
    )


class SpecificationFile(_Strict):
    """``curriculum/specs/<board>-<code>.yaml``."""

    specification: SpecificationHeader
    topics: list[TopicEntry] = Field(min_length=1)
    set_texts: list[SetTextGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        _require_unique("topic ref", [t.ref for t in self.topics])
        refs = [o.ref for t in self.topics for s in t.subtopics for o in s.objectives]
        _require_unique("objective ref", refs)
        for topic in self.topics:
            _require_unique(
                f"subtopic title in topic {topic.ref}", [s.title for s in topic.subtopics]
            )
        if not self.specification.tiered:
            for topic in self.topics:
                for sub in topic.subtopics:
                    for obj in sub.objectives:
                        if obj.higher is not None or obj.foundation is None:
                            raise ValueError(
                                f"objective {obj.ref}: untiered specs use 'foundation' only"
                            )
        _require_unique("set text category", [g.category for g in self.set_texts])
        for group in self.set_texts:
            _require_unique(f"set text in {group.category}", [o.title for o in group.options])
        return self


def _normalise(value: str) -> str:
    return " ".join(value.lower().split())


def _require_unique(what: str, values: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {what}: {value!r}")
        seen.add(value)
