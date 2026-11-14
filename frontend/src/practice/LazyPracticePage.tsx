// frontend/src/practice/LazyPracticePage.tsx
import { lazy, Suspense } from "react";

import type { UserOut } from "../api/generated/model";
import { FullPageMessage } from "../components/FullPageMessage";

// Practice pulls in KaTeX (large), so it's loaded only when first opened.
const PracticePage = lazy(() =>
  import("./PracticePage").then((m) => ({ default: m.PracticePage })),
);

/** The practice screen, code-split from the main bundle. */
export function LazyPracticePage({ user }: { user: UserOut }) {
  return (
    <Suspense fallback={<FullPageMessage busy>Loading…</FullPageMessage>}>
      <PracticePage user={user} />
    </Suspense>
  );
}
