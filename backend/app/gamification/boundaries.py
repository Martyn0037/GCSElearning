# backend/app/gamification/boundaries.py
"""Admin-entered grade boundaries (percent per grade) for estimating boss battle grade bands."""

from __future__ import annotations

import itertools
import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidRequestError, NotFoundError
from app.gamification.schemas import GradeBoundariesIn, GradeBoundariesOut, GradeBoundaryIn
from app.models.curriculum import Specification, Tier
from app.models.gamification import GradeBoundary

# Grades each tier can award (Foundation 1-5, Higher 4-9 with an allowed 3).
TIER_GRADES: dict[str | None, range] = {
    "foundation": range(1, 6),
    "higher": range(3, 10),
    None: range(1, 10),
}


async def _spec(session: AsyncSession, specification_id: uuid.UUID) -> Specification:
    spec = await session.get(Specification, specification_id)
    if spec is None:
        raise NotFoundError("Specification not found")
    return spec


async def list_boundaries(
    session: AsyncSession, specification_id: uuid.UUID
) -> list[GradeBoundariesOut]:
    """Boundaries for a spec, one entry per tier that has any."""
    await _spec(session, specification_id)
    rows = (
        await session.scalars(
            select(GradeBoundary)
            .where(GradeBoundary.specification_id == specification_id)
            .order_by(GradeBoundary.tier, GradeBoundary.grade)
        )
    ).all()
    by_tier: dict[Tier | None, list[GradeBoundaryIn]] = defaultdict(list)
    for row in rows:
        by_tier[row.tier].append(GradeBoundaryIn(grade=row.grade, min_percent=row.min_percent))
    return [
        GradeBoundariesOut(
            specification_id=specification_id,
            tier=tier.value if tier else None,
            boundaries=entries,
        )
        for tier, entries in by_tier.items()
    ]


async def replace_boundaries(
    session: AsyncSession, specification_id: uuid.UUID, body: GradeBoundariesIn
) -> GradeBoundariesOut:
    """Replace one tier's boundaries (an empty list clears them). Commits.

    Raises:
        NotFoundError: Unknown spec.
        InvalidRequestError: A grade outside the tier, a repeated grade, or
            percentages that don't rise with the grade.
    """
    await _spec(session, specification_id)
    allowed = TIER_GRADES[body.tier]
    grades = [b.grade for b in body.boundaries]
    if any(g not in allowed for g in grades):
        raise InvalidRequestError(
            f"Grades for this tier must be between {allowed.start} and {allowed.stop - 1}."
        )
    if len(set(grades)) != len(grades):
        raise InvalidRequestError("Each grade can appear only once.")
    ordered = sorted(body.boundaries, key=lambda b: b.grade)
    if any(a.min_percent >= b.min_percent for a, b in itertools.pairwise(ordered)):
        raise InvalidRequestError("Higher grades need higher percentages.")
    tier = Tier(body.tier) if body.tier else None
    tier_match = GradeBoundary.tier.is_(None) if tier is None else GradeBoundary.tier == tier
    await session.execute(
        delete(GradeBoundary).where(GradeBoundary.specification_id == specification_id, tier_match)
    )
    for boundary in ordered:
        session.add(
            GradeBoundary(
                specification_id=specification_id,
                tier=tier,
                grade=boundary.grade,
                min_percent=boundary.min_percent,
            )
        )
    await session.commit()
    return GradeBoundariesOut(specification_id=specification_id, tier=body.tier, boundaries=ordered)
