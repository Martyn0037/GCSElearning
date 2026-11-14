// frontend/src/progress/MistakesPage.tsx
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import {
  getListMyMistakesQueryKey,
  listMyMistakes,
  useMyMistakeGroups,
} from "../api/generated/endpoints";
import type { MistakeOut, MistakeTopicGroup, UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";
import { MathText } from "../practice/MathText";

const PAGE_SIZE = 20;

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** "My mistakes": counts by topic and misconception, then each mistake with its explanation. */
export function MistakesPage({ user }: { user: UserOut }) {
  const [fixed, setFixed] = useState(false);
  const groups = useMyMistakeGroups();

  return (
    <AppShell user={user}>
      <Link to="/" className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ Home
      </Link>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">My mistakes</h1>
      <p className="text-slate-700">
        Each one comes back for review until you get it right twice in a row.
      </p>

      {groups.isSuccess && groups.data.length > 0 && <GroupSummary groups={groups.data} />}

      <div role="tablist" aria-label="Which mistakes" className="mt-6 flex gap-2">
        {[
          [false, "To fix"],
          [true, "Fixed"],
        ].map(([value, label]) => (
          <button
            key={String(label)}
            type="button"
            role="tab"
            aria-selected={fixed === value}
            onClick={() => {
              setFixed(Boolean(value));
            }}
            className={`min-h-11 rounded-full px-4 font-medium ${fixed === value ? "bg-brand-700 text-white" : "bg-white text-slate-800 shadow-sm"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <MistakeList key={String(fixed)} fixed={fixed} />
    </AppShell>
  );
}

function GroupSummary({ groups }: { groups: readonly MistakeTopicGroup[] }) {
  return (
    <section aria-label="Mistakes by topic" className="mt-4 space-y-2">
      {groups.map((group) => (
        <div key={group.topicId} className="rounded-xl bg-white p-3 shadow-sm">
          <p className="font-semibold text-slate-900">
            {group.subjectName}: {group.topicRef}. {group.topicTitle}
          </p>
          <p className="text-sm text-slate-600">
            {group.open} to fix · {group.fixed} fixed
          </p>
          {group.misconceptions.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {group.misconceptions.map((m) => (
                <li
                  key={m.label}
                  className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-900"
                >
                  {m.label} ×{m.count}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}

function MistakeList({ fixed }: { fixed: boolean }) {
  const params = { fixed, limit: PAGE_SIZE };
  const pages = useInfiniteQuery({
    queryKey: getListMyMistakesQueryKey(params),
    queryFn: ({ pageParam, signal }) =>
      listMyMistakes({ ...params, ...(pageParam ? { cursor: pageParam } : {}) }, { signal }),
    initialPageParam: "",
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });

  if (pages.isPending)
    return (
      <p role="status" className="mt-4">
        Loading…
      </p>
    );
  if (pages.isError)
    return (
      <p role="alert" className="mt-4">
        Couldn&apos;t load your mistakes. Please refresh.
      </p>
    );
  const items = pages.data.pages.flatMap((p) => p.items);
  if (items.length === 0) {
    return (
      <p className="mt-4 text-slate-700">
        {fixed ? "Nothing fixed yet. Keep going!" : "No mistakes to fix. Nice work!"}
      </p>
    );
  }
  return (
    <>
      <ul className="mt-4 space-y-3">
        {items.map((mistake) => (
          <li key={mistake.id}>
            <MistakeCard mistake={mistake} />
          </li>
        ))}
      </ul>
      {pages.hasNextPage && (
        <button
          type="button"
          onClick={() => void pages.fetchNextPage()}
          disabled={pages.isFetchingNextPage}
          className="mt-4 min-h-11 w-full rounded-lg bg-white font-medium shadow-sm disabled:opacity-60"
        >
          {pages.isFetchingNextPage ? "Loading…" : "Show more"}
        </button>
      )}
    </>
  );
}

function MistakeCard({ mistake }: { mistake: MistakeOut }) {
  return (
    <article className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-600">
        {mistake.subjectName} · {mistake.topicTitle} · Skill {mistake.objectiveRef}
      </p>
      <p className="text-slate-900">
        <MathText text={mistake.questionStem} />
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-600">Your answer</dt>
        <dd className="text-red-800">
          {mistake.assisted ? "Used the full solution" : <MathText text={mistake.studentAnswer} />}
        </dd>
        <dt className="text-slate-600">Correct</dt>
        <dd className="text-green-800">
          <MathText text={mistake.correctAnswer} />
        </dd>
      </dl>
      {mistake.explanation && (
        <p className="rounded-lg bg-brand-50 p-3 text-sm text-slate-800">
          <MathText text={mistake.explanation} />
        </p>
      )}
      <p className="text-sm font-medium text-slate-700">
        {mistake.resolved
          ? "✓ Fixed"
          : mistake.nextReviewOn
            ? `Back for review on ${formatDate(mistake.nextReviewOn)}`
            : null}
      </p>
    </article>
  );
}
