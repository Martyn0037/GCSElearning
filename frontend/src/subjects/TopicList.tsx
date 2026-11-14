// frontend/src/subjects/TopicList.tsx
import { Link } from "react-router";

import type { TopicOut } from "../api/generated/model";

/**
 * A subject's topics in study order, showing which are unlocked.
 * With ``enrolmentId``, unlocked topics get a "Practise" button.
 */
export function TopicList({
  topics,
  enrolmentId,
}: {
  topics: readonly TopicOut[];
  enrolmentId?: string;
}) {
  if (topics.length === 0) {
    return <p className="text-slate-700">No topics have been added for this subject yet.</p>;
  }
  return (
    <ol className="space-y-3">
      {topics.map((topic) => (
        <li
          key={topic.id}
          className={`rounded-xl p-4 shadow-sm ${topic.unlocked ? "bg-white" : "bg-slate-100"}`}
        >
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              <span className="text-slate-500">{topic.ref}.</span> {topic.title}
            </h2>
            {topic.unlocked ? (
              <span className="rounded-full bg-green-100 px-3 py-1 text-sm text-green-900">
                Ready
              </span>
            ) : (
              <span className="rounded-full bg-slate-200 px-3 py-1 text-sm text-slate-700">
                <span aria-hidden="true">🔒 </span>Not covered yet
              </span>
            )}
          </div>
          <ul className="mt-2 space-y-1 text-slate-700">
            {topic.subtopics.map((subtopic) => (
              <li key={subtopic.id} className="flex justify-between gap-3">
                <span>{subtopic.title}</span>
                <span className="shrink-0 whitespace-nowrap text-sm text-slate-500">
                  {subtopic.objectiveCount} {subtopic.objectiveCount === 1 ? "skill" : "skills"}
                </span>
              </li>
            ))}
          </ul>
          {enrolmentId && topic.unlocked && (
            <Link
              to={`/practice/${enrolmentId}/${topic.id}`}
              className="mt-3 flex min-h-12 items-center justify-center rounded-lg bg-brand-700 font-semibold text-white hover:bg-brand-800"
            >
              Practise {topic.title}
            </Link>
          )}
        </li>
      ))}
    </ol>
  );
}
