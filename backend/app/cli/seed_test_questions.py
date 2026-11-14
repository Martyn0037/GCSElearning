# backend/app/cli/seed_test_questions.py
"""Insert a few fixed questions for end-to-end tests. NOT for real use.

These questions are hand-written test fixtures, not generated or checked
content, so the command refuses to run when ENVIRONMENT=production.

Usage::

    python -m app.cli.seed_test_questions --spec 1MA1 --objective N4
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid

from sqlalchemy import select

from app.core.config import Environment, get_settings
from app.db.session import create_engine, create_session_factory
from app.models.curriculum import LearningObjective, Specification, Tier
from app.models.question import Hint, Question, QuestionStatus, QuestionType

FIXTURES = [
    {
        "stem": "E2E: Write down the highest common factor of $12$ and $18$.",
        "options": [["A", "2"], ["B", "3"], ["C", "6"], ["D", "36"]],
        "correct": "C",
    },
    {
        "stem": "E2E: Write down the lowest common multiple of $4$ and $6$.",
        "options": [["A", "2"], ["B", "12"], ["C", "24"], ["D", "10"]],
        "correct": "B",
    },
]


async def _run(spec_code: str, ref: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            objective = await session.scalar(
                select(LearningObjective)
                .join(Specification, Specification.id == LearningObjective.specification_id)
                .where(Specification.code == spec_code, LearningObjective.ref == ref)
            )
            if objective is None:
                sys.exit(f"Objective {ref} not found in {spec_code}")
            for tier in (Tier.FOUNDATION, Tier.HIGHER):
                for difficulty in range(1, 6):
                    for fixture in FIXTURES:
                        digest = hashlib.sha256(
                            f"{fixture['stem']}|{tier}|{difficulty}".encode()
                        ).hexdigest()
                        exists = await session.scalar(
                            select(Question.id).where(
                                Question.objective_id == objective.id,
                                Question.content_hash == digest,
                            )
                        )
                        if exists:
                            continue
                        question = Question(
                            id=uuid.uuid4(),
                            objective_id=objective.id,
                            tier=tier,
                            difficulty=difficulty,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            command_word="Write down",
                            stem=str(fixture["stem"]),
                            options=[{"label": a, "text": b} for a, b in fixture["options"]],
                            answer={"correct_option": fixture["correct"]},
                            marks=1,
                            worked_solution="E2E fixture worked solution.",
                            status=QuestionStatus.ACTIVE,
                            verified=True,
                            confidence=1.0,
                            generator_model="e2e-fixture",
                            content_hash=digest,
                        )
                        session.add(question)
                        await session.flush()
                        session.add_all(
                            Hint(question_id=question.id, level=i, text=f"E2E hint {i}")
                            for i in range(1, 5)
                        )
            await session.commit()
    finally:
        await engine.dispose()
    print("Seeded end-to-end test questions.")


def main() -> None:
    """Parse arguments and seed, unless in production."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--objective", required=True)
    args = parser.parse_args()
    if get_settings().environment is Environment.PRODUCTION:
        sys.exit("Refusing to seed test questions in production.")
    asyncio.run(_run(args.spec, args.objective))


if __name__ == "__main__":
    main()
