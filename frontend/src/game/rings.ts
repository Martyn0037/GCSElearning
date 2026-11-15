// frontend/src/game/rings.ts
import type { Ring as RingValue } from "../api/generated/model";

/** Each ring's name and colour. */
export const RINGS: Record<RingValue, { label: string; colour: string }> = {
  none: { label: "No ring yet", colour: "var(--color-slate-400)" },
  bronze: { label: "Bronze", colour: "#c2701c" },
  silver: { label: "Silver", colour: "#8b9bb4" },
  gold: { label: "Gold", colour: "#eab308" },
  exam_ready: { label: "Exam ready", colour: "#16a34a" },
};

/** The ring's name, e.g. "Gold". */
export function ringLabel(ring: RingValue): string {
  return RINGS[ring].label;
}
