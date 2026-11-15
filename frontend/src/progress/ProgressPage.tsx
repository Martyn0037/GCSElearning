// frontend/src/progress/ProgressPage.tsx
import { useParams } from "react-router";

import { useMySubjectProgress } from "../api/generated/endpoints";
import type { ObjectiveStat, TopicProgress, UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";
import { BackLink, ErrorNotice, LoadingCards } from "../components/ui";
import { MathText } from "../practice/MathText";
import { ActivityChart } from "./ActivityChart";
import { MasteryRing } from "../game/Ring";

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Progress for one subject: mastery by topic, recent activity, strongest and weakest skills. */
export function ProgressPage({ user }: { user: UserOut }) {
  const { enrolmentId = "" } = useParams();
  const progress = useMySubjectProgress(enrolmentId);

  return (
    <AppShell user={user}>
      <BackLink to={`/subjects/${enrolmentId}`}>Back to topics</BackLink>
      {progress.isPending && <LoadingCards rows={3} />}
      {progress.isError && (
        <ErrorNotice>Couldn&apos;t load your progress. Please refresh.</ErrorNotice>
      )}
      {progress.isSuccess && (
        <div className="mt-2 space-y-8">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {progress.data.subjectName}: progress
          </h1>

          <section aria-labelledby="mastery-heading" className="space-y-3">
            <h2 id="mastery-heading" className="text-lg font-semibold">
              How well you know each topic
            </h2>
            <ul className="space-y-3">
              {progress.data.topics.map((topic) => (
                <TopicBar key={topic.topicId} topic={topic} />
              ))}
            </ul>
          </section>

          <section aria-labelledby="activity-heading" className="space-y-3">
            <h2 id="activity-heading" className="text-lg font-semibold">
              Last 30 days
            </h2>
            <ActivityChart daily={progress.data.daily} />
          </section>

          {progress.data.strongest.length > 0 && (
            <div className="grid gap-6 sm:grid-cols-2">
              <SkillList title="Strongest skills" skills={progress.data.strongest} />
              {progress.data.weakest.length > 0 && (
                <SkillList title="Skills to work on" skills={progress.data.weakest} />
              )}
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}

function TopicBar({ topic }: { topic: TopicProgress }) {
  const value = Math.round(topic.mastery * 100);
  return (
    <li>
      <div className="flex justify-between gap-3 text-slate-800">
        <span>
          <span className="text-slate-500">{topic.ref}.</span> {topic.title}
        </span>
        <span className="font-semibold">{percent(topic.mastery)}</span>
      </div>
      {topic.ring && topic.ring !== "none" && <MasteryRing ring={topic.ring} />}
      <div
        role="progressbar"
        aria-label={`${topic.title} mastery`}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        className="mt-1 h-3 w-full overflow-hidden rounded-full bg-slate-200"
      >
        <div className="h-full rounded-full bg-brand-600" style={{ width: `${value}%` }} />
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {topic.objectivesPractised} of {topic.objectivesTotal} skills practised
        {topic.accuracy !== null ? ` · ${percent(topic.accuracy)} right` : ""}
      </p>
    </li>
  );
}

function SkillList({ title, skills }: { title: string; skills: readonly ObjectiveStat[] }) {
  return (
    <section aria-label={title}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="mt-2 space-y-2">
        {skills.map((skill) => (
          <li key={skill.ref} className="rounded-lg bg-surface p-3 shadow-sm">
            <span className="font-semibold">{skill.ref}</span>{" "}
            <span className="text-slate-700">
              <MathText text={skill.text} />
            </span>
            <span className="block text-sm text-slate-600">
              {percent(skill.mastery)} · {skill.attempts}{" "}
              {skill.attempts === 1 ? "answer" : "answers"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
