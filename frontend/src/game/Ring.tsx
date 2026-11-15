// frontend/src/game/Ring.tsx
import type { Ring as RingValue } from "../api/generated/model";
import { RINGS, ringLabel } from "./rings";

/**
 * A ring drawn as an SVG progress circle.
 *
 * Args:
 *   ring: Which ring the topic has.
 *   progress: How far towards the next ring, 0-1.
 *   size: Diameter in pixels.
 */
export function RingIcon({
  ring,
  progress = 1,
  size = 24,
}: {
  ring: RingValue;
  progress?: number;
  size?: number;
}) {
  const { colour } = RINGS[ring];
  const stroke = size >= 40 ? 5 : 4;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = ring === "exam_ready" ? 1 : Math.max(0, Math.min(progress, 1));
  const centre = size / 2;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${String(size)} ${String(size)}`}
      aria-hidden="true"
    >
      <circle
        cx={centre}
        cy={centre}
        r={radius}
        fill="none"
        stroke="var(--color-slate-200)"
        strokeWidth={stroke}
      />
      <circle
        cx={centre}
        cy={centre}
        r={radius}
        fill="none"
        stroke={colour}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${String(circumference * filled)} ${String(circumference)}`}
        transform={`rotate(-90 ${String(centre)} ${String(centre)})`}
        className="transition-[stroke-dasharray] duration-700"
      />
    </svg>
  );
}

/** A topic's mastery ring: a coloured circle filled by progress, with its name. */
export function MasteryRing({ ring, progress = 1 }: { ring: RingValue; progress?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-slate-700">
      <RingIcon ring={ring} progress={progress} />
      {ringLabel(ring)}
    </span>
  );
}
