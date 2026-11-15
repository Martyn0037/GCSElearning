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
          <span className="xp-pop rounded-full bg-gradient-to-r from-amber-400 to-orange-500 px-3 py-1 font-bold text-white shadow-sm">
            +{earned} XP
          </span>
        )}
        {rewards.streakExtended && (
          <span className="rounded-full bg-orange-50 px-3 py-1 font-medium text-orange-900">
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
        <p className="font-semibold text-brand-ink">
          Challenge complete: +{rewards.bonusXp} bonus XP
        </p>
      )}
      {rewards.levelUp && (
        <p className="animate-pop rounded-2xl bg-gradient-to-br from-brand-500 to-brand-800 p-4 text-center text-lg font-bold text-white shadow-brand">
          Level {rewards.level} reached!
        </p>
      )}
      {rewards.newBadges.map((badge) => (
        <p key={badge.code} className="animate-pop rounded-2xl bg-amber-50 p-4 text-amber-900">
          <span aria-hidden="true" className="mr-1 text-xl">
            🏅
          </span>
          <span className="font-semibold">New badge: {badge.name}</span>
          <span className="block text-sm">{badge.description}</span>
        </p>
      ))}
    </div>
  );
}
