# backend/app/cli/eval_questions.py
"""Content-quality evaluation: generate N questions per objective and report.

Every question goes through the normal pipeline (generate -> verify -> SymPy),
so this measures what the student would actually get. It spends real money,
within the configured budget caps, so it asks for ``--yes``.

Usage::

    python -m app.cli.eval_questions --spec 1MA1 --count 3 --difficulty 2 --tier higher --yes
    python -m app.cli.eval_questions --spec 1MA1 --objective N4 --objective N8 --count 5 --yes

Prints the pass rate per objective and lists every rejected question with
the reasons, so you can spot-check them. Rejected questions are stored with
status ``rejected`` and are never shown to the student.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from app.ai.factory import build_breaker, build_generator, build_llm_client
from app.ai.gateway import AiUnavailableError
from app.core.clock import SystemClock
from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models.curriculum import LearningObjective, Specification, Tier
from app.models.question import Question, QuestionStatus


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    client = build_llm_client(settings)
    if client is None:
        print("ANTHROPIC_API_KEY is not set; nothing to evaluate.")
        return 1
    clock = SystemClock()
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    tier = Tier(args.tier) if args.tier else None
    try:
        async with sessions() as session:
            query = (
                select(LearningObjective)
                .join(Specification, Specification.id == LearningObjective.specification_id)
                .where(
                    Specification.code == args.spec,
                    Specification.is_current.is_(True),
                    LearningObjective.retired_at.is_(None),
                )
                .order_by(LearningObjective.position)
            )
            if args.objective:
                query = query.where(LearningObjective.ref.in_(args.objective))
            objectives = [o for o in (await session.scalars(query)).all() if o.text_for(tier)]
        if not objectives:
            print("No matching objectives on that tier.")
            return 1

        generator = build_generator(
            settings, sessions, client, build_breaker(settings, clock), clock
        )
        started = clock.now()
        totals: Counter[str] = Counter()
        for objective in objectives:
            served = 0
            for _ in range(args.count):
                try:
                    if await generator.generate(objective.id, tier, args.difficulty):
                        served += 1
                except AiUnavailableError as exc:
                    print(f"  {objective.ref}: stopped ({exc.reason}: {exc})")
                    if exc.reason in {"budget", "circuit_open"}:
                        return 2
            totals["served"] += served
            totals["attempted"] += args.count
            print(f"{objective.ref}: {served}/{args.count} passed")

        async with sessions() as session:
            rejected = (
                await session.execute(
                    select(LearningObjective.ref, Question.stem, Question.verification_notes)
                    .join(LearningObjective, LearningObjective.id == Question.objective_id)
                    .where(
                        Question.created_at >= started, Question.status == QuestionStatus.REJECTED
                    )
                    .order_by(LearningObjective.ref)
                )
            ).all()
        rate = totals["served"] / totals["attempted"] if totals["attempted"] else 0.0
        print(f"\nPass rate: {totals['served']}/{totals['attempted']} ({rate:.0%})")
        if rejected:
            print("\nRejected questions (spot-check these):")
            for ref, stem, notes in rejected:
                print(f"- [{ref}] {stem[:140]}\n    reasons: {notes}")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    """Parse arguments and run the evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate generated question quality")
    parser.add_argument("--spec", required=True, help="spec code, e.g. 1MA1")
    parser.add_argument(
        "--objective", action="append", help="objective ref (repeatable); default all"
    )
    parser.add_argument("--count", type=int, default=3, help="questions per objective")
    parser.add_argument("--difficulty", type=int, default=2, choices=range(1, 6))
    parser.add_argument("--tier", choices=[t.value for t in Tier])
    parser.add_argument(
        "--yes", action="store_true", help="confirm: this calls Claude and costs money"
    )
    args = parser.parse_args()
    if not args.yes:
        sys.exit(
            "This calls the Claude API (within your budget caps). Re-run with --yes to proceed."
        )
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
