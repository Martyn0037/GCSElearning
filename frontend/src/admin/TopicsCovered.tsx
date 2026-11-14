// frontend/src/admin/TopicsCovered.tsx
import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  getGetEnrolmentTopicsQueryKey,
  useGetEnrolmentTopics,
  useListEnrolments,
  useSetTopicOrder,
  useSetTopicTaught,
} from "../api/generated/endpoints";
import type { TopicMapOut, TopicOut } from "../api/generated/model";

/** Pick a student's subject, then tick topics covered at school and set their order. */
export function TopicsCovered() {
  const enrolments = useListEnrolments({ limit: 100 });
  const [enrolmentId, setEnrolmentId] = useState("");
  const selectId = useId();

  if (enrolments.isPending) return <p role="status">Loading…</p>;
  if (enrolments.isError) return <p role="alert">Couldn&apos;t load subjects. Please refresh.</p>;
  const active = enrolments.data.items.filter((e) => e.status === "active");
  if (active.length === 0) {
    return <p className="text-slate-700">No subjects are ready yet.</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor={selectId} className="font-medium">
          Subject
        </label>
        <select
          id={selectId}
          value={enrolmentId}
          onChange={(e) => {
            setEnrolmentId(e.target.value);
          }}
          className="mt-1 block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2"
        >
          <option value="">Choose a subject…</option>
          {active.map((e) => (
            <option key={e.id} value={e.id}>
              {e.studentName}: {e.subjectName}
            </option>
          ))}
        </select>
      </div>
      {enrolmentId && <TopicEditor enrolmentId={enrolmentId} />}
    </div>
  );
}

function TopicEditor({ enrolmentId }: { enrolmentId: string }) {
  const map = useGetEnrolmentTopics(enrolmentId);
  const queryClient = useQueryClient();
  const taught = useSetTopicTaught();
  const order = useSetTopicOrder();

  if (map.isPending) return <p role="status">Loading…</p>;
  if (map.isError) return <p role="alert">Couldn&apos;t load topics. Please refresh.</p>;

  function store(result: TopicMapOut) {
    queryClient.setQueryData(getGetEnrolmentTopicsQueryKey(enrolmentId), result);
  }

  function move(topics: readonly TopicOut[], index: number, delta: -1 | 1) {
    const ids = topics.map((t) => t.id);
    const target = index + delta;
    const [moved] = ids.splice(index, 1);
    if (moved === undefined) return;
    ids.splice(target, 0, moved);
    order.mutate({ enrolmentId, data: { topicIds: ids } }, { onSuccess: store });
  }

  const topics = map.data.topics;
  return (
    <ol className="space-y-2" aria-busy={taught.isPending || order.isPending}>
      {topics.map((topic, index) => (
        <li
          key={topic.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3 shadow-sm"
        >
          <label className="flex min-h-11 flex-1 cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={topic.taughtAtSchool}
              onChange={(e) => {
                taught.mutate(
                  { enrolmentId, topicId: topic.id, data: { taughtAtSchool: e.target.checked } },
                  { onSuccess: store },
                );
              }}
              aria-label={`${topic.ref}. ${topic.title}: covered at school`}
              className="size-6 accent-brand-700"
            />
            <span aria-hidden="true">
              <span className="text-slate-500">{topic.ref}.</span> {topic.title}
            </span>
          </label>
          <span className="flex gap-1">
            <button
              type="button"
              disabled={index === 0 || order.isPending}
              onClick={() => {
                move(topics, index, -1);
              }}
              aria-label={`Move ${topic.title} up`}
              className="min-h-11 min-w-11 rounded-lg border border-slate-300 disabled:opacity-40"
            >
              ↑
            </button>
            <button
              type="button"
              disabled={index === topics.length - 1 || order.isPending}
              onClick={() => {
                move(topics, index, 1);
              }}
              aria-label={`Move ${topic.title} down`}
              className="min-h-11 min-w-11 rounded-lg border border-slate-300 disabled:opacity-40"
            >
              ↓
            </button>
          </span>
        </li>
      ))}
    </ol>
  );
}
