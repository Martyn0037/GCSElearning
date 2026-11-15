// frontend/src/test/fixtures.ts
// Shared test data.
import type { TopicStandingOut } from "../api/generated/model";

/** A topic with no ring and a locked boss battle. */
export const NO_STANDING: TopicStandingOut = {
  ring: "none",
  ringProgress: 0,
  bossUnlocked: false,
  skillsToUnlockBoss: 1,
  bossBest: null,
};
