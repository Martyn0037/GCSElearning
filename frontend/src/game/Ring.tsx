// frontend/src/game/Ring.tsx
import type { Ring as RingValue } from "../api/generated/model";

const RINGS: Record<RingValue, { label: string; colour: string }> = {
  none: { label: "No ring yet", colour: "#cbd5e1" },
  bronze: { label: "Bronze", colour: "#b45309" },
  silver: { label: "Silver", colour: "#64748b" },
  gold: { label: "Gold", colour: "#ca8a04" },
  exam_ready: { label: "Exam ready", colour: "#15803d" },
};

/** A topic's mastery ring: a coloured circle filled by progress, with its name. */
export function MasteryRing({ ring, progress = 1 }: { ring: RingValue; progress?: number }) {
  const { label, colour } = RINGS[ring];
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const filled = ring === "exam_ready" ? 1 : Math.max(0, Math.min(progress, 1));
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-slate-700">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="4" />
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke={colour}
          strokeWidth="4"
          strokeDasharray={`${String(circumference * filled)} ${String(circumference)}`}
          transform="rotate(-90 12 12)"
        />
      </svg>
      {label}
    </span>
  );
}
