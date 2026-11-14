# backend/app/enrolment/schemas.py
"""Request/response bodies for the catalogue, subject choice, topic map and admin tools."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.core.schemas import ApiModel
from app.models.curriculum import Tier

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Author = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

MAX_SUBJECTS = 20
MAX_SET_TEXTS_PER_SUBJECT = 12


# ---------------------------------------------------------------- catalogue


class BoardOut(ApiModel):
    """An exam board."""

    id: uuid.UUID
    code: str
    name: str


class SetTextOptionOut(ApiModel):
    """A set text on a board's list."""

    id: uuid.UUID
    category: str
    title: str
    author: str | None


class SpecificationOut(ApiModel):
    """An imported specification version."""

    id: uuid.UUID
    board_id: uuid.UUID
    code: str
    title: str
    version: str
    tiered: bool


class CatalogueSpecificationOut(SpecificationOut):
    """A current specification, with its set-text list (if any)."""

    set_texts: list[SetTextOptionOut]


class CatalogueSubjectOut(ApiModel):
    """A subject the student can choose."""

    id: uuid.UUID
    slug: str
    name: str
    has_tiers: bool
    set_text_categories: list[str]
    most_common_board_id: uuid.UUID | None
    specifications: list[CatalogueSpecificationOut] = Field(
        description="Current imported specs; a board without one is 'being set up'"
    )


class CatalogueOut(ApiModel):
    """Everything the setup screen needs."""

    boards: list[BoardOut]
    subjects: list[CatalogueSubjectOut]


# ---------------------------------------------------------------- choices (input)


class SetTextChoice(ApiModel):
    """One set text: an option from the board's list, or a typed-in title."""

    category: Name
    option_id: uuid.UUID | None = None
    custom_title: Title | None = None
    custom_author: Author | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.option_id is None) == (self.custom_title is None):
            raise ValueError("give either optionId or customTitle")
        if self.option_id is not None and self.custom_author is not None:
            raise ValueError("customAuthor only goes with customTitle")
        return self


class SubjectChoice(ApiModel):
    """One subject from the setup screen.

    ``board_id`` null means "I don't know" (the most common board is used and
    flagged for the admin). ``tier`` null means "not sure" (Higher is used and
    flagged), or that the subject has no tiers.
    """

    subject_id: uuid.UUID | None = None
    custom_name: Name | None = None
    board_id: uuid.UUID | None = None
    tier: Tier | None = None
    set_texts: list[SetTextChoice] = Field(
        default_factory=list, max_length=MAX_SET_TEXTS_PER_SUBJECT
    )

    @model_validator(mode="after")
    def _catalogue_or_custom(self) -> Self:
        if (self.subject_id is None) == (self.custom_name is None):
            raise ValueError("give either subjectId or customName")
        return self


class SubjectChoices(ApiModel):
    """The full list of the student's subjects (replaces the previous list)."""

    subjects: list[SubjectChoice] = Field(min_length=1, max_length=MAX_SUBJECTS)


# ---------------------------------------------------------------- enrolments (output)


class EnrolmentStatus(StrEnum):
    """``active``: questions available. ``pending``: waiting for the admin/spec."""

    ACTIVE = "active"
    PENDING = "pending"


class StudentSetTextOut(ApiModel):
    """A set text the student studies."""

    id: uuid.UUID
    category: str
    title: str
    author: str | None
    status: EnrolmentStatus


class EnrolmentOut(ApiModel):
    """One of the student's subjects."""

    id: uuid.UUID
    subject_id: uuid.UUID | None
    subject_name: str
    is_custom: bool
    board_id: uuid.UUID | None
    board_name: str | None
    board_confirmed: bool
    tier: Tier | None
    tier_confirmed: bool
    status: EnrolmentStatus
    specification: SpecificationOut | None
    set_texts: list[StudentSetTextOut]


class MySubjectsOut(ApiModel):
    """The student's subjects."""

    setup_completed: bool
    subjects: list[EnrolmentOut]


class AttentionReason(StrEnum):
    """Why an admin should look at an enrolment."""

    NO_SPECIFICATION = "no_specification"
    BOARD_UNCONFIRMED = "board_unconfirmed"
    TIER_UNCONFIRMED = "tier_unconfirmed"
    SET_TEXT_PENDING = "set_text_pending"


class AdminEnrolmentOut(EnrolmentOut):
    """An enrolment as the admin sees it."""

    student_id: uuid.UUID
    student_name: str
    attention: list[AttentionReason]


class AdminEnrolmentPage(ApiModel):
    """A page of enrolments."""

    items: list[AdminEnrolmentOut]
    next_cursor: str | None


class EnrolmentUpdate(ApiModel):
    """Admin corrections. Any field given counts as confirmed."""

    board_id: uuid.UUID | None = None
    tier: Tier | None = None
    specification_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _something(self) -> Self:
        if self.board_id is None and self.tier is None and self.specification_id is None:
            raise ValueError("give at least one of boardId, tier, specificationId")
        return self


class SetTextUpdate(ApiModel):
    """Admin matching a typed-in set text to a board option."""

    option_id: uuid.UUID


class AdminSpecificationOut(SpecificationOut):
    """An imported spec with content counts."""

    subject_name: str
    board_name: str
    is_current: bool
    topic_count: int
    objective_count: int
    source_file: str


# ---------------------------------------------------------------- topic map


class SubtopicOut(ApiModel):
    """A heading inside a topic."""

    id: uuid.UUID
    title: str
    objective_count: int


class TopicOut(ApiModel):
    """A topic on the student's map."""

    id: uuid.UUID
    ref: str
    title: str
    taught_at_school: bool
    unlocked: bool
    subtopics: list[SubtopicOut]


class TopicMapOut(ApiModel):
    """A subject's topics in the student's order."""

    enrolment_id: uuid.UUID
    subject_name: str
    tier: Tier | None
    specification: SpecificationOut
    topics: list[TopicOut]


class TopicSettingUpdate(ApiModel):
    """Admin: whether a topic has been covered at school."""

    taught_at_school: bool


class TopicOrderUpdate(ApiModel):
    """Admin: the full topic order for one enrolment."""

    topic_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
