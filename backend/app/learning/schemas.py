# backend/app/learning/schemas.py
"""Request/response bodies for learn cards and the tutor, and Claude's output shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.schemas import ApiModel
from app.models.learning import TutorRole

MAX_TUTOR_MESSAGE = 500


class TutorAsk(ApiModel):
    """A student's message to the tutor."""

    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TUTOR_MESSAGE)
    ]


class TutorMessageOut(ApiModel):
    """One message in the conversation."""

    id: uuid.UUID
    role: TutorRole
    content: str
    created_at: datetime


class TutorThreadOut(ApiModel):
    """The conversation about one question."""

    messages: list[TutorMessageOut]
    remaining: int = Field(description="Messages the student can still send about this question")


class LearnCardOut(ApiModel):
    """A short explanation and worked example for the question's skill."""

    objective_ref: str
    objective_text: str
    explanation: str
    worked_example: str


class TutorReply(BaseModel):
    """What Claude returns for a tutor turn."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(description="Your reply to the student, 1-4 short sentences")
    on_topic: bool = Field(
        description="False if the student's message isn't about this question, its topic, "
        "or studying for it"
    )


class LearnCardDraft(BaseModel):
    """What Claude returns for a learn card."""

    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(description="A short explanation of the skill, 3-6 sentences")
    worked_example: str = Field(description="One worked example, step by step")
