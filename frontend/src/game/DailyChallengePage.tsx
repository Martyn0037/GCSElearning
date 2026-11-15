// frontend/src/game/DailyChallengePage.tsx
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { Link } from "react-router";

import { getChallenge, nextChallengeItem, startDaily } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { buttonClass } from "../components/styles";
import { PracticeSession } from "../practice/PracticeSession";

const START_ERRORS: Record<string, string> = {
  NOTHING_TO_PRACTISE: "There's nothing to practise yet: choose your subjects first.",
  QUESTIONS_PREPARING: "We're preparing today's challenge. Try again in a minute.",
};

/** Today's daily challenge: 5 mixed questions, then a summary. */
export function DailyChallengePage({ user }: { user: UserOut }) {
  // Starting is idempotent (one challenge per day), so a query is fine here.
  const challenge = useQuery({ queryKey: ["daily-challenge"], queryFn: () => startDaily() });

  if (challenge.isPending) {
    return (
      <AppShell user={user}>
        <p role="status">Getting today&apos;s challenge…</p>
      </AppShell>
    );
  }
  if (challenge.isError) {
    const error = challenge.error;
    const message =
      error instanceof ApiError ? (START_ERRORS[error.code] ?? error.message) : "Please try again.";
    return (
      <AppShell user={user}>
        <div role="alert" className="space-y-3 rounded-xl bg-amber-50 p-4 text-amber-900">
          <p>{message}</p>
          <Link to="/" className={buttonClass("secondary")}>
            Home
          </Link>
        </div>
      </AppShell>
    );
  }
  return <DailySession user={user} challengeId={challenge.data.id} />;
}

function DailySession({ user, challengeId }: { user: UserOut; challengeId: string }) {
  const fetchNext = useCallback(() => nextChallengeItem(challengeId), [challengeId]);
  return (
    <PracticeSession
      user={user}
      fetchNext={fetchNext}
      back={{ to: "/", label: "Home" }}
      done={{ code: "CHALLENGE_FINISHED", content: <DailySummary challengeId={challengeId} /> }}
    />
  );
}

function DailySummary({ challengeId }: { challengeId: string }) {
  const query = useQuery({
    queryKey: ["challenge", challengeId],
    queryFn: () => getChallenge(challengeId),
  });
  if (!query.isSuccess) return <p role="status">Adding it up…</p>;
  const data = query.data;
  return (
    <div className="space-y-3 rounded-xl bg-green-50 p-4 text-green-900">
      <p className="text-xl font-semibold">Daily challenge done!</p>
      <p>
        {data.score} of {data.maxScore} right
        {data.bonusXp ? ` · +${String(data.bonusXp)} bonus XP` : ""}
      </p>
      <Link to="/" className={buttonClass("primary", true, "lg")}>
        Back home
      </Link>
    </div>
  );
}
