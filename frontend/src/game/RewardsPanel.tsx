// frontend/src/game/RewardsPanel.tsx
import { useEffect } from "react";

import type { ChallengeProgressOut, RewardsOut } from "../api/generated/model";
import { playCue } from "./sound";

/**
 * What an answer earned: XP (with a small pop), streak, level up and new
 * badges. Encouraging, never guilt-tripping: a wrong answer just shows nothing.
 */
export function RewardsPanel({
  rewards,
  challenge,
}: {
  rewards: RewardsOut;
  challenge?: ChallengeProgressOut | null;
}) {
  const earned = rewards.xpGained + rewards.bonusXp;
  useEffect(() => {
    if (rewards.newBadges.length > 0) playCue("badge");
    else if (rewards.levelUp) playCue("levelUp");
    else if (rewards.xpGained > 0) playCue("correct");
  }, [rewards]);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {earned > 0 && (
          <span className="xp-pop rounded-full bg-brand-50 px-3 py-1 font-semibold text-brand-800">
            +{earned} XP
          </span>
        )}
        {rewards.streakExtended && (
          <span className="rounded-full bg-orange-50 px-3 py-1 text-orange-900">
            <span aria-hidden="true">🔥 </span>
            {rewards.streakDays}-day streak
          </span>
        )}
        {challenge && !challenge.completed && (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
            {challenge.answered} of {challenge.total} done
          </span>
        )}
      </div>
      {rewards.usedFreeze && (
        <p className="text-sm text-slate-600">
          Your weekly streak freeze covered the day you missed.
        </p>
      )}
      {rewards.bonusXp > 0 && (
        <p className="font-semibold text-brand-800">
          Challenge complete: +{rewards.bonusXp} bonus XP
        </p>
      )}
      {rewards.levelUp && (
        <p className="rounded-lg bg-brand-700 p-3 font-semibold text-white">
          Level {rewards.level} reached!
        </p>
      )}
      {rewards.newBadges.map((badge) => (
        <p key={badge.code} className="rounded-lg bg-amber-50 p-3 text-amber-900">
          <span aria-hidden="true">🏅 </span>
          <span className="font-semibold">New badge: {badge.name}</span>
          <span className="block text-sm">{badge.description}</span>
        </p>
      ))}
    </div>
  );
}
