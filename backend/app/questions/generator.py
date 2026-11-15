# backend/app/questions/generator.py
"""Generate, check and store one question for one objective at one difficulty.

Pipeline (brief section 4):
1. Haiku writes the question as structured JSON for exactly one objective;
   it's validated (schema + rules) and retried on failure.
2. A second Haiku call solves it independently and checks scope, tier,
   difficulty, hints and mark scheme.
3. Numeric answers are re-computed with SymPy in a sandbox.
4. Only questions that pass everything become ``active`` (or
   ``pending_review`` in strict mode); others are stored as ``rejected`` for
   the evaluation report and never shown.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import AiGateway, AiRequest
from app.core.config import Settings
from app.models.curriculum import (
    ExamBoard,
    LearningObjective,
    Specification,
    Subject,
    Subtopic,
    Tier,
    Topic,
)
from app.models.question import Hint, Question, QuestionStatus, QuestionType
from app.questions.llm_schemas import GeneratedQuestion, Verification
from app.questions.marking import normalise_text, parse_number
from app.questions.prompts import (
    GENERATION_SYSTEM,
    VERIFICATION_SYSTEM,
    ObjectiveContext,
    generation_user_prompt,
    verification_user_prompt,
)
from app.questions.sympy_check import CheckOutcome, check_numeric_answer
from app.questions.validation import check_generated

logger = logging.getLogger(__name__)

# Question types tried at each level, rotated so the bank stays varied.
# Quantitative subjects lean on numbers; essay subjects on written answers.
TYPES_BY_LEVEL: dict[int, tuple[QuestionType, ...]] = {
    1: (QuestionType.MULTIPLE_CHOICE, QuestionType.SHORT_TEXT),
    2: (QuestionType.MULTIPLE_CHOICE, QuestionType.NUMERIC),
    3: (QuestionType.NUMERIC, QuestionType.MULTIPLE_CHOICE),
    4: (QuestionType.NUMERIC, QuestionType.SHORT_TEXT),
    5: (QuestionType.NUMERIC, QuestionType.SHORT_TEXT, QuestionType.EXTENDED),
}
ESSAY_TYPES_BY_LEVEL: dict[int, tuple[QuestionType, ...]] = {
    1: (QuestionType.MULTIPLE_CHOICE, QuestionType.SHORT_TEXT),
    2: (QuestionType.MULTIPLE_CHOICE, QuestionType.SHORT_TEXT),
    3: (QuestionType.SHORT_TEXT, QuestionType.EXTENDED),
    4: (QuestionType.EXTENDED, QuestionType.SHORT_TEXT),
    5: (QuestionType.EXTENDED,),
}
QUANTITATIVE_SUBJECTS = frozenset(
    {"maths", "combined-science", "biology", "chemistry", "physics", "computer-science"}
)


def types_for(subject_slug: str, difficulty: int) -> tuple[QuestionType, ...]:
    """Question types to rotate through for a subject at a level."""
    table = TYPES_BY_LEVEL if subject_slug in QUANTITATIVE_SUBJECTS else ESSAY_TYPES_BY_LEVEL
    return table[difficulty]


class ObjectiveNotAvailableError(Exception):
    """The objective doesn't exist, is retired, or isn't on the requested tier."""


async def load_context(
    session: AsyncSession, objective_id: uuid.UUID, tier: Tier | None
) -> ObjectiveContext:
    """Gather the curriculum facts for a prompt in one query.

    Raises:
        ObjectiveNotAvailableError: If it can't be used for this tier.
    """
    row = (
        await session.execute(
            select(
                LearningObjective,
                Subtopic.title,
                Topic.title,
                Specification,
                Subject.name,
                ExamBoard.name,
                Subject.slug,
            )
            .join(Subtopic, Subtopic.id == LearningObjective.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(Specification, Specification.id == LearningObjective.specification_id)
            .join(Subject, Subject.id == Specification.subject_id)
            .join(ExamBoard, ExamBoard.id == Specification.board_id)
            .where(LearningObjective.id == objective_id, LearningObjective.retired_at.is_(None))
        )
    ).first()
    if row is None:
        raise ObjectiveNotAvailableError("objective not found")
    objective, subtopic, topic, spec, subject, board, slug = row
    wording = objective.text_for(tier if spec.tiered else None)
    if wording is None:
        raise ObjectiveNotAvailableError("objective not on this tier")
    return ObjectiveContext(
        subject=subject,
        board=board,
        subject_slug=slug,
        spec_code=spec.code,
        spec_version=spec.version,
        topic=topic,
        subtopic=subtopic,
        objective_ref=objective.ref,
        objective_text=wording,
        keywords=tuple(objective.keywords),
        out_of_scope=objective.out_of_scope,
        tier=tier if spec.tiered else None,
    )


@dataclass(frozen=True, slots=True)
class Decision:
    """Whether a generated question may be served."""

    status: QuestionStatus
    verified: bool
    confidence: float
    notes: str


_OPTION_WORD = re.compile(r"\boption\s*\(?([A-Da-d])\b", re.IGNORECASE)
_OPTION_LETTER = re.compile(r"\b([A-D])\b")
# An optional "x =" before the number, e.g. "b = 11 (because 27/99 = 3/11)".
_LEADING_NUMBER = re.compile(r"^\s*(?:[A-Za-z]\w*\s*=\s*)?([-\u2212]?[\d.,]+(?:/[\d.,]+)?)")
_PARENTHESES = re.compile(r"\([^)]*\)")


def _solved_option(solved: str) -> str | None:
    """The option letter in answers like "C", "c)", "450 (option C)"."""
    if len(normalise_text(solved)) == 1:
        return normalise_text(solved)
    match = _OPTION_WORD.search(solved) or _OPTION_LETTER.search(solved)
    return match.group(1).lower() if match else None


def _verifier_agrees(q: GeneratedQuestion, v: Verification) -> bool:
    """Check the verifier's own answer against the key, independently of its yes/no.

    The verifier is asked for a bare answer but sometimes adds working, so the
    letter or leading number is extracted rather than compared verbatim.
    """
    solved = v.solved_answer.strip()
    if q.question_type == "extended":
        return True  # no single answer: judged by answer_is_correct and the mark scheme
    if q.question_type == "multiple_choice":
        return _solved_option(solved) == (q.correct_option or "").lower()
    if q.question_type == "numeric":
        expected = parse_number(q.numeric_answer or "")
        tolerance = Fraction(Decimal(q.numeric_tolerance or "0"))
        match = _LEADING_NUMBER.match(solved)
        given = parse_number(match.group(1).rstrip(".,")) if match else None
        return (
            expected is not None
            and given is not None
            and abs(given - expected) <= max(tolerance, Fraction(1, 10**9))
        )
    accepted = {normalise_text(a) for a in q.accepted_answers}
    return (
        normalise_text(solved) in accepted
        or normalise_text(_PARENTHESES.sub(" ", solved)) in accepted
    )


def decide(
    q: GeneratedQuestion, v: Verification, sympy: CheckOutcome, settings: Settings
) -> Decision:
    """Combine every check into a serve / don't-serve decision."""
    failures = []
    if not v.answer_is_correct:
        failures.append("verifier says the key is wrong")
    if not _verifier_agrees(q, v):
        failures.append(f"verifier's own answer {v.solved_answer!r} differs from the key")
    if not v.within_objective:
        failures.append("outside the objective")
    if not v.suitable_for_tier:
        failures.append("unsuitable for tier")
    if v.hints_reveal_answer_early:
        failures.append("hints give the answer away")
    if not v.mark_scheme_consistent:
        failures.append("mark scheme inconsistent")
    if sympy is CheckOutcome.MISMATCH:
        failures.append("SymPy re-computation disagrees with the answer")
    confidence = min(max(v.confidence, 0.0), 1.0)
    if confidence < settings.question_min_confidence:
        failures.append(f"confidence {confidence:.2f} below threshold")
    notes = "; ".join(failures + [f"verifier: {i}" for i in v.issues])[:2000]
    if failures:
        return Decision(QuestionStatus.REJECTED, False, confidence, notes)
    status = (
        QuestionStatus.PENDING_REVIEW if settings.question_strict_mode else QuestionStatus.ACTIVE
    )
    return Decision(status, True, confidence, notes)


def _answer_key(q: GeneratedQuestion) -> dict[str, object]:
    if q.question_type == "multiple_choice":
        return {"correct_option": q.correct_option}
    if q.question_type == "numeric":
        return {"value": q.numeric_answer, "tolerance": q.numeric_tolerance or "0", "unit": q.unit}
    if q.question_type == "extended":
        return {
            "marking_points": [p.model_dump() for p in q.marking_points],
            "levels": [level.model_dump() for level in q.level_descriptors],
            "model_answer": q.model_answer,
        }
    return {"accepted": q.accepted_answers}


def content_hash(q: GeneratedQuestion) -> str:
    """Fingerprint for spotting duplicate questions on the same objective."""
    basis = normalise_text(q.stem) + "|" + normalise_text(str(sorted(_answer_key(q).items())))
    return hashlib.sha256(basis.encode()).hexdigest()


class QuestionGenerator:
    """Creates checked questions on demand (worker jobs, or the API when the bank is empty)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: AiGateway,
        settings: Settings,
    ) -> None:
        """Create the generator."""
        self._sessions = session_factory
        self._gateway = gateway
        self._settings = settings

    async def generate(
        self, objective_id: uuid.UUID, tier: Tier | None, difficulty: int
    ) -> Question | None:
        """Generate, verify and store one question.

        Returns:
            The stored question if it may be served, else ``None`` (rejected or
            a duplicate).

        Raises:
            AiUnavailableError: If Claude can't be used (no key, budget, outage).
            ObjectiveNotAvailableError: If the objective can't be used.
        """
        async with self._sessions() as session:
            ctx = await load_context(session, objective_id, tier)
            existing = (
                await session.scalars(
                    select(Question.stem)
                    .where(Question.objective_id == objective_id, Question.difficulty == difficulty)
                    .order_by(Question.created_at.desc())
                    .limit(5)
                )
            ).all()
            count = await session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.objective_id == objective_id)
            )
        types = types_for(ctx.subject_slug, difficulty)
        question_type = types[(count or 0) % len(types)]

        generated = await self._gateway.structured(
            AiRequest(
                purpose="generate_question",
                model=self._settings.model_generation,
                system=GENERATION_SYSTEM,
                user=generation_user_prompt(ctx, difficulty, question_type.value, list(existing)),
                schema=GeneratedQuestion,
                max_tokens=8000,
            ),
            check=lambda q: check_generated(q, question_type.value),
        )
        verification = await self._gateway.structured(
            AiRequest(
                purpose="verify_question",
                model=self._settings.model_verification,
                system=VERIFICATION_SYSTEM,
                user=verification_user_prompt(ctx, difficulty, generated.model_dump_json()),
                schema=Verification,
                max_tokens=8000,
            )
        )
        sympy = CheckOutcome.UNCHECKED
        if generated.question_type == "numeric":
            sympy = await check_numeric_answer(
                generated.check_expression,
                Fraction(Decimal(generated.numeric_answer or "0")),
                Fraction(Decimal(generated.numeric_tolerance or "0")),
            )
        decision = decide(generated, verification, sympy, self._settings)
        return await self._store(objective_id, ctx.tier, difficulty, generated, decision, sympy)

    async def _store(
        self,
        objective_id: uuid.UUID,
        tier: Tier | None,
        difficulty: int,
        q: GeneratedQuestion,
        decision: Decision,
        sympy: CheckOutcome,
    ) -> Question | None:
        digest = content_hash(q)
        async with self._sessions() as session, session.begin():
            duplicate = await session.scalar(
                select(Question.id).where(
                    Question.objective_id == objective_id, Question.content_hash == digest
                )
            )
            if duplicate is not None:
                logger.info("question_duplicate", extra={"objective_id": str(objective_id)})
                return None
            question = Question(
                id=uuid.uuid4(),
                objective_id=objective_id,
                tier=tier,
                difficulty=difficulty,
                question_type=QuestionType(q.question_type),
                command_word=q.command_word,
                stem=q.stem,
                options=[o.model_dump() for o in q.options] or None,
                answer=_answer_key(q),
                marks=q.marks,
                worked_solution=q.worked_solution,
                status=decision.status,
                verified=decision.verified,
                confidence=decision.confidence,
                verification_notes=decision.notes or None,
                sympy_checked=sympy is CheckOutcome.MATCH,
                generator_model=self._settings.model_generation,
                content_hash=digest,
            )
            session.add(question)
            await session.flush()
            session.add_all(
                Hint(question_id=question.id, level=i + 1, text=t) for i, t in enumerate(q.hints)
            )
        logger.info(
            "question_generated",
            extra={
                "objective_id": str(objective_id),
                "status": decision.status.value,
                "difficulty": difficulty,
            },
        )
        return question if decision.status is QuestionStatus.ACTIVE else None
