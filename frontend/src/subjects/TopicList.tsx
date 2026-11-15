// frontend/src/subjects/TopicList.tsx
import { Link } from "react-router";

import type { TopicOut } from "../api/generated/model";
import { MasteryRing } from "../game/Ring";

/**
 * A subject's topics in study order, each with its mastery ring.
 * Every topic is open (ADR-021); with ``enrolmentId`` each gets a "Practise" button.
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
        <li key={topic.id} className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">
            <span className="text-slate-500">{topic.ref}.</span> {topic.title}
          </h2>
          <div className="mt-2">
            <MasteryRing ring={topic.standing.ring} progress={topic.standing.ringProgress} />
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
          {enrolmentId && (
            <Link
              to={`/practice/${enrolmentId}/${topic.id}`}
              className="mt-3 flex min-h-12 items-center justify-center rounded-lg bg-brand-700 font-semibold text-white hover:bg-brand-800"
            >
              Practise {topic.title}
            </Link>
          )}
          {enrolmentId && <BossButton topic={topic} enrolmentId={enrolmentId} />}
        </li>
      ))}
    </ol>
  );
}

function BossButton({ topic, enrolmentId }: { topic: TopicOut; enrolmentId: string }) {
  const { bossUnlocked, skillsToUnlockBoss, bossBest } = topic.standing;
  if (!bossUnlocked) {
    return (
      <p className="mt-2 text-sm text-slate-600">
        <span aria-hidden="true">⚔️ </span>Boss battle: practise {skillsToUnlockBoss} more{" "}
        {skillsToUnlockBoss === 1 ? "skill" : "skills"} to unlock
      </p>
    );
  }
  return (
    <Link
      to={`/boss/${enrolmentId}/${topic.id}`}
      className="mt-2 flex min-h-12 items-center justify-center rounded-lg border-2 border-brand-700 font-semibold text-brand-800 hover:bg-brand-50"
    >
      <span aria-hidden="true">⚔️&nbsp;</span>Boss battle
      {bossBest != null && <span className="ml-2 text-sm font-normal">(best {bossBest}%)</span>}
    </Link>
  );
}
