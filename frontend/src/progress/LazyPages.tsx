// frontend/src/progress/LazyPages.tsx
import { lazy, Suspense } from "react";

import type { UserOut } from "../api/generated/model";
import { FullPageMessage } from "../components/FullPageMessage";

// Code-split: these pull in KaTeX (mistakes, review, challenges) and Recharts (progress).
const MistakesPage = lazy(() =>
  import("./MistakesPage").then((m) => ({ default: m.MistakesPage })),
);
const ProgressPage = lazy(() =>
  import("./ProgressPage").then((m) => ({ default: m.ProgressPage })),
);
const ReviewPage = lazy(() =>
  import("../practice/PracticePage").then((m) => ({ default: m.ReviewPage })),
);

const DailyChallengePage = lazy(() =>
  import("../game/DailyChallengePage").then((m) => ({ default: m.DailyChallengePage })),
);
const BossBattlePage = lazy(() =>
  import("../game/BossBattlePage").then((m) => ({ default: m.BossBattlePage })),
);

function Loading() {
  return <FullPageMessage busy>Loading…</FullPageMessage>;
}

export function LazyMistakesPage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<Loading />}>
      <MistakesPage user={user} />
    </Suspense>
  );
}

export function LazyProgressPage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<Loading />}>
      <ProgressPage user={user} />
    </Suspense>
  );
}

export function LazyReviewPage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<Loading />}>
      <ReviewPage user={user} />
    </Suspense>
  );
}

export function LazyDailyChallengePage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<Loading />}>
      <DailyChallengePage user={user} />
    </Suspense>
  );
}

export function LazyBossBattlePage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<Loading />}>
      <BossBattlePage user={user} />
    </Suspense>
  );
}
