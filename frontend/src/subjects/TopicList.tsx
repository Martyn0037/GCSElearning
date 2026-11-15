// frontend/src/subjects/TopicList.tsx
import { Link } from "react-router";

import type { TopicOut } from "../api/generated/model";
import { Icon } from "../components/Icon";
import { EmptyState } from "../components/ui";
import { buttonClass, cardClass } from "../components/styles";
import { RingIcon } from "../game/Ring";
import { ringLabel } from "../game/rings";

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
    return (
      <EmptyState icon="book" title="No topics yet">
        No topics have been added for this subject yet.
      </EmptyState>
    );
  }
  return (
    <ol className="space-y-3">
      {topics.map((topic) => {
        const skills = topic.subtopics.reduce((sum, s) => sum + s.objectiveCount, 0);
        const { ring, ringProgress } = topic.standing;
        return (
          <li key={topic.id} className={`${cardClass} p-4`}>
            <div className="flex items-start gap-3">
              <span className="relative grid shrink-0 place-items-center">
                <RingIcon ring={ring} progress={ringProgress} size={44} />
                <span className="absolute text-xs font-bold text-slate-600">{topic.ref}</span>
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="leading-snug font-semibold text-slate-900">
                  <span className="sr-only">{`${topic.ref}. ${topic.title}`}</span>
                  <span aria-hidden="true">{topic.title}</span>
                </h2>
                <p className="mt-0.5 text-sm text-slate-600">
                  <span>{ringLabel(ring)}</span> · {skills} {skills === 1 ? "skill" : "skills"}
                </p>
              </div>
            </div>
            {topic.subtopics.length > 0 && (
              <details className="group mt-3 rounded-xl bg-slate-50 px-3 open:pb-2">
                <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between text-sm font-medium text-slate-700 [&::-webkit-details-marker]:hidden">
                  {topic.subtopics.length} {topic.subtopics.length === 1 ? "section" : "sections"}
                  <Icon
                    name="chevronDown"
                    className="size-4 text-slate-500 transition-transform group-open:rotate-180"
                  />
                </summary>
                <ul className="space-y-1 text-sm text-slate-700">
                  {topic.subtopics.map((subtopic) => (
                    <li key={subtopic.id} className="flex justify-between gap-3 py-0.5">
                      <span>{subtopic.title}</span>
                      <span className="shrink-0 whitespace-nowrap text-slate-500">
                        {subtopic.objectiveCount}{" "}
                        {subtopic.objectiveCount === 1 ? "skill" : "skills"}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {enrolmentId && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Link
                  to={`/practice/${enrolmentId}/${topic.id}`}
                  aria-label={`Practise ${topic.title}`}
                  className={`${buttonClass("primary")} flex-1`}
                >
                  Practise
                  <Icon name="chevronRight" className="size-4" />
                </Link>
                <BossButton topic={topic} enrolmentId={enrolmentId} />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function BossButton({ topic, enrolmentId }: { topic: TopicOut; enrolmentId: string }) {
  const { bossUnlocked, skillsToUnlockBoss, bossBest } = topic.standing;
  if (!bossUnlocked) {
    return (
      <p className="flex w-full items-center gap-1.5 text-xs text-slate-600">
        <Icon name="swords" className="size-4 text-slate-400" />
        Boss battle: practise {skillsToUnlockBoss} more{" "}
        {skillsToUnlockBoss === 1 ? "skill" : "skills"} to unlock
      </p>
    );
  }
  return (
    <Link to={`/boss/${enrolmentId}/${topic.id}`} className={`${buttonClass("secondary")} flex-1`}>
      <Icon name="swords" className="size-4" />
      Boss battle
      {bossBest != null && <span className="font-normal text-slate-600">(best {bossBest}%)</span>}
    </Link>
  );
}
