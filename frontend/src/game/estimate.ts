// frontend/src/game/estimate.ts
import type { GradeEstimateOut } from "../api/generated/model";

/** "around 5–6", or a plain description when no grade boundaries are set. */
export function describeEstimate(grade: GradeEstimateOut): string {
  const standing = { secure: "secure", developing: "developing", not_yet: "not yet secure" }[
    grade.standing
  ];
  if (grade.bandLow != null && grade.bandHigh != null) {
    const band =
      grade.bandLow === grade.bandHigh
        ? `around grade ${String(grade.bandLow)}`
        : `around grade ${String(grade.bandLow)}–${String(grade.bandHigh)}`;
    return `${band} (${standing})`;
  }
  if (grade.belowLowestGrade != null) {
    return `below grade ${String(grade.belowLowestGrade)} for now (${standing})`;
  }
  return standing;
}
