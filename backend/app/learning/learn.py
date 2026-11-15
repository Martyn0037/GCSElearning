# backend/app/learning/learn.py
"""Learn cards: a short explanation and one worked example per objective and tier.

Generated once in the background (Haiku), cached, and reviewable: in strict
mode new cards wait for the admin. Only curriculum data goes into the prompt.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import AiGateway, AiRequest
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.jobs.queue import enqueue
from app.learning.schemas import LearnCardDraft, LearnCardOut
from app.models.curriculum import LearningObjective, Specification, Tier
from app.models.enrolment import StudentSubject
from app.models.learning import LearnCard, LearnCardStatus
from app.models.question import PracticeItem, Question
from app.questions.generator import load_context
from app.questions.prompts import DIFFICULTY_DESCRIPTIONS, ObjectiveContext

logger = logging.getLogger(__name__)

LEARN_JOB = "generate_learn_card"
MAX_EXPLANATION = 1500
MAX_EXAMPLE = 2500
_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

LEARN_SYSTEM = """\
You write short "learn" cards for a student in England studying the reformed (9-1) GCSE.

Each card covers exactly one learning objective, quoted from the official specification in the request, at the stated tier. Don't teach content outside it or listed as out of scope.
- explanation: 3-6 clear sentences in UK English for a 14-16 year old: what the skill is, the key idea or rule, and a common mistake to avoid.
- worked_example: one typical GCSE-style example, set out step by step as a student would write it, ending with the answer.
Write mathematics in LaTeX between single dollar signs. No HTML, links, images or Markdown headings. Never claim to be official exam board material, and never use real people's names.
"""


def check_card(card: LearnCardDraft) -> str | None:
    """Reject empty, over-long or marked-up cards (the gateway retries)."""
    if not card.explanation.strip() or len(card.explanation) > MAX_EXPLANATION:
        return "explanation empty or too long"
    if not card.worked_example.strip() or len(card.worked_example) > MAX_EXAMPLE:
        return "worked example empty or too long"
    if _HTML_TAG.search(card.explanation) or _HTML_TAG.search(card.worked_example):
        return "contains HTML markup"
    return None


def user_prompt(ctx: ObjectiveContext) -> str:
    """The per-card prompt: curriculum facts only."""
    lines = [
        f"Subject: {ctx.subject} ({ctx.board} {ctx.spec_code}, {ctx.spec_version}).",
        f"Topic: {ctx.topic} > {ctx.subtopic}.",
        f"Objective {ctx.objective_ref}: {ctx.objective_text}",
        "Tier: untiered subject." if ctx.tier is None else f"Tier: {ctx.tier.value.capitalize()}.",
        f"Pitch the example at: {DIFFICULTY_DESCRIPTIONS[2]}",
    ]
    if ctx.out_of_scope:
        lines.append(f"Out of scope: {ctx.out_of_scope}")
    return "\n".join(lines)


def _tier_match(tier: Tier | None):  # type: ignore[no-untyped-def]
    return LearnCard.tier.is_(None) if tier is None else LearnCard.tier == tier


async def card_for_item(
    session: AsyncSession,
    settings: Settings,
    student_id: uuid.UUID,
    item_id: uuid.UUID,
    now: datetime,
) -> LearnCardOut:
    """The learn card for a practice item's skill, or queue one.

    Raises:
        NotFoundError: Unknown or someone else's question.
        ConflictError: ``LEARN_PREPARING`` while a card is written or reviewed;
            ``LEARN_UNAVAILABLE`` when cards can't be generated (no API key).
    """
    item = await session.get(PracticeItem, item_id)
    if item is None or item.user_id != student_id:
        raise NotFoundError("Question not found")
    question = await session.get(Question, item.question_id)
    enrolment = await session.get(StudentSubject, item.enrolment_id)
    assert question is not None  # noqa: S101 - FK guarantees it
    assert enrolment is not None  # noqa: S101 - FK guarantees it
    objective = await session.get(LearningObjective, question.objective_id)
    assert objective is not None  # noqa: S101 - FK guarantees it
    spec = await session.get(Specification, objective.specification_id)
    tier = enrolment.tier if spec is not None and spec.tiered else None
    card = await session.scalar(
        select(LearnCard).where(LearnCard.objective_id == objective.id, _tier_match(tier))
    )
    if card is not None and card.status is LearnCardStatus.ACTIVE:
        return LearnCardOut(
            objective_ref=objective.ref,
            objective_text=objective.text_for(tier) or objective.foundation_text or "",
            explanation=card.explanation,
            worked_example=card.worked_example,
        )
    if card is not None:  # pending review or rejected: nothing to show yet
        raise ConflictError("This skill's learn card is being checked.", code="LEARN_PREPARING")
    if settings.anthropic_api_key is None:
        raise ConflictError("Learn cards aren't available yet.", code="LEARN_UNAVAILABLE")
    await enqueue(
        session,
        LEARN_JOB,
        {"objective_id": str(objective.id), "tier": tier.value if tier else None},
        now,
        dedupe_key=f"learn:{objective.id}:{tier.value if tier else '-'}",
    )
    await session.commit()
    raise ConflictError(
        "We're writing this skill's learn card. Try again in a minute.", code="LEARN_PREPARING"
    )


class LearnCardWriter:
    """Writes learn cards (run by the worker)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: AiGateway,
        settings: Settings,
    ) -> None:
        """Create the writer."""
        self._sessions = session_factory
        self._gateway = gateway
        self._settings = settings

    async def write(self, objective_id: uuid.UUID, tier: Tier | None) -> LearnCardStatus | None:
        """Write and store one card, unless one exists already. Idempotent.

        Returns:
            The stored card's status, or ``None`` if a card already existed.

        Raises:
            AiUnavailableError: Claude can't be used.
            ObjectiveNotAvailableError: The objective can't be used on this tier.
        """
        async with self._sessions() as session:
            existing = await session.scalar(
                select(LearnCard.id).where(
                    LearnCard.objective_id == objective_id, _tier_match(tier)
                )
            )
            if existing is not None:
                return None
            ctx = await load_context(session, objective_id, tier)
        draft = await self._gateway.structured(
            AiRequest(
                purpose="learn_card",
                model=self._settings.model_generation,
                system=LEARN_SYSTEM,
                user=user_prompt(ctx),
                schema=LearnCardDraft,
                max_tokens=3000,
            ),
            check=check_card,
        )
        status = (
            LearnCardStatus.PENDING_REVIEW
            if self._settings.question_strict_mode
            else LearnCardStatus.ACTIVE
        )
        async with self._sessions() as session, session.begin():
            await session.execute(
                insert(LearnCard)
                .values(
                    id=uuid.uuid4(),
                    objective_id=objective_id,
                    tier=ctx.tier,
                    explanation=draft.explanation.strip(),
                    worked_example=draft.worked_example.strip(),
                    status=status,
                    generator_model=self._settings.model_generation,
                )
                .on_conflict_do_nothing()
            )
        logger.info("learn_card_written", extra={"status": status.value})
        return status
