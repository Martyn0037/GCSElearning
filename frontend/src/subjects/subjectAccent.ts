// frontend/src/subjects/subjectAccent.ts
/**
 * A stable accent colour per subject (tile background + text), so each
 * subject is recognisable at a glance. The same name always gets the same
 * colour; the palette uses tints that the dark theme remaps.
 */
const ACCENTS = [
  "bg-brand-100 text-brand-ink",
  "bg-green-100 text-green-800",
  "bg-amber-100 text-amber-900",
  "bg-red-100 text-red-800",
  "bg-slate-200 text-slate-800",
] as const;

/**
 * Tailwind classes for a subject's accent tile.
 *
 * Args:
 *   name: The subject's display name.
 *
 * Returns:
 *   Background and text classes.
 */
export function subjectAccent(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return ACCENTS[hash % ACCENTS.length] ?? ACCENTS[0];
}
