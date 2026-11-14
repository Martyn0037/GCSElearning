// frontend/src/subjects/TopicMapPage.tsx
import { Link, useParams } from "react-router";

import { useGetMyTopicMap } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { TopicList } from "./TopicList";

/** A subject's topic map for the student. */
export function TopicMapPage({ user }: { user: UserOut }) {
  const { enrolmentId = "" } = useParams();
  const map = useGetMyTopicMap(enrolmentId);

  return (
    <AppShell user={user}>
      <Link to="/" className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ Back to subjects
      </Link>
      {map.isPending && <p role="status">Loading…</p>}
      {map.isError && (
        <p role="alert" className="mt-4 rounded-lg bg-amber-50 p-3 text-amber-900">
          {map.error instanceof ApiError && map.error.code === "SUBJECT_NOT_READY"
            ? "This subject is still being set up. Check back soon."
            : map.error instanceof ApiError && map.error.status === 404
              ? "We couldn't find that subject."
              : "Couldn't load this subject. Please refresh."}
        </p>
      )}
      {map.isSuccess && (
        <>
          <div className="mt-2 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl font-bold text-slate-900">{map.data.subjectName}</h1>
            <Link
              to={`/progress/${map.data.enrolmentId}`}
              className="inline-flex min-h-11 items-center text-brand-700 underline"
            >
              Progress
            </Link>
          </div>
          <p className="mb-4 text-sm text-slate-600">
            {map.data.specification.code} · {map.data.specification.version}
            {map.data.tier ? ` · ${map.data.tier === "higher" ? "Higher" : "Foundation"} tier` : ""}
          </p>
          {map.data.topics.every((t) => !t.unlocked) && map.data.topics.length > 0 && (
            <p className="mb-4 rounded-lg bg-brand-50 p-3 text-slate-800">
              Topics unlock once they&apos;re marked as covered at school. Ask your parent or carer
              to tick off what you&apos;ve done so far.
            </p>
          )}
          <TopicList topics={map.data.topics} enrolmentId={map.data.enrolmentId} />
        </>
      )}
    </AppShell>
  );
}
