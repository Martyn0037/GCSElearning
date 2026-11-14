// frontend/src/practice/PracticePage.tsx
import { useCallback } from "react";
import { Link, useParams } from "react-router";

import { nextPracticeItem, nextReviewItem } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { PracticeSession } from "./PracticeSession";

/** Practise one topic. */
export function PracticePage({ user }: { user: UserOut }) {
  const { enrolmentId = "", topicId = "" } = useParams();
  const fetchNext = useCallback(
    () => nextPracticeItem(enrolmentId, topicId),
    [enrolmentId, topicId],
  );
  return (
    <PracticeSession
      user={user}
      fetchNext={fetchNext}
      back={{ to: `/subjects/${enrolmentId}`, label: "Back to topics" }}
    />
  );
}

/** Work through the mistakes due for review today. */
export function ReviewPage({ user }: { user: UserOut }) {
  return (
    <PracticeSession
      user={user}
      fetchNext={nextReviewItem}
      back={{ to: "/", label: "Home" }}
      done={{
        code: "NO_REVIEWS_DUE",
        content: (
          <div className="space-y-3 rounded-xl bg-green-50 p-4 text-green-900">
            <p className="text-lg font-semibold">All caught up for today. ✓</p>
            <Link to="/mistakes" className="inline-flex min-h-11 items-center underline">
              See my mistakes
            </Link>
          </div>
        ),
      }}
    />
  );
}
