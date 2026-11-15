// frontend/src/practice/PracticePage.tsx
import { useCallback } from "react";
import { Link, useParams } from "react-router";

import { nextPracticeItem, nextReviewItem } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { buttonClass } from "../components/styles";
import { EmptyState } from "../components/ui";
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
          <EmptyState icon="check" title="All caught up for today.">
            <Link to="/mistakes" className={`${buttonClass("secondary")} mt-2`}>
              See my mistakes
            </Link>
          </EmptyState>
        ),
      }}
    />
  );
}
