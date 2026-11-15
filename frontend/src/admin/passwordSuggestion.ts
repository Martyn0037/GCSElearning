// frontend/src/admin/passwordSuggestion.ts
/**
 * Easy-to-type password suggestions for a student, e.g. "maple-rocket-otter-42".
 *
 * Three words from a list of 64 plus two digits gives about 25 bits of
 * entropy: fine behind the login rate limit and lockout, and easy for a
 * teenager to type on a phone. Uses the browser's cryptographic random source.
 */

/** Matches the backend's limits (app/auth/passwords.py). */
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;

const WORDS = [
  "acorn",
  "amber",
  "anchor",
  "apple",
  "arrow",
  "badger",
  "banjo",
  "beacon",
  "birch",
  "bison",
  "bright",
  "cactus",
  "candle",
  "canyon",
  "cedar",
  "cobalt",
  "comet",
  "coral",
  "cosmic",
  "crystal",
  "dolphin",
  "ember",
  "falcon",
  "fern",
  "forest",
  "galaxy",
  "garnet",
  "glacier",
  "harbour",
  "hazel",
  "heron",
  "island",
  "jasper",
  "jungle",
  "kettle",
  "lantern",
  "lemon",
  "lunar",
  "maple",
  "meadow",
  "meteor",
  "mango",
  "nebula",
  "nimbus",
  "oasis",
  "orbit",
  "otter",
  "panda",
  "pebble",
  "pepper",
  "pixel",
  "planet",
  "puffin",
  "quartz",
  "raven",
  "ripple",
  "rocket",
  "saffron",
  "summit",
  "thunder",
  "tiger",
  "tulip",
  "velvet",
  "willow",
] as const;

type RandomFill = (buffer: Uint32Array<ArrayBuffer>) => Uint32Array<ArrayBuffer>;

function randomIndex(size: number, random: RandomFill): number {
  // Rejection sampling avoids modulo bias.
  const limit = Math.floor(0x1_0000_0000 / size) * size;
  const buffer = new Uint32Array(1);
  for (;;) {
    const value = random(buffer)[0] ?? 0;
    if (value < limit) return value % size;
  }
}

/**
 * A new suggested password.
 *
 * Args:
 *   random: Fills a buffer with random values (defaults to ``crypto.getRandomValues``;
 *     injectable for tests).
 *
 * Returns:
 *   Three words and two digits joined by hyphens.
 */
export function suggestPassword(
  random: RandomFill = (buffer) => crypto.getRandomValues(buffer),
): string {
  const words = Array.from({ length: 3 }, () => WORDS[randomIndex(WORDS.length, random)]);
  const digits = String(randomIndex(90, random) + 10);
  return [...words, digits].join("-");
}

/**
 * Why a new password can't be used yet, or null if it can.
 *
 * Args:
 *   password: The new password.
 *   confirm: The same password typed again.
 */
export function passwordProblem(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${String(MIN_PASSWORD_LENGTH)} characters.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Use at most ${String(MAX_PASSWORD_LENGTH)} characters.`;
  }
  if (password !== confirm) return "The two passwords don't match.";
  return null;
}
