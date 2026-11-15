// frontend/src/admin/AdminPage.tsx
import type { ReactNode } from "react";

import { useListSpecifications } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";
import { AttentionList } from "./AttentionList";
import { Costs } from "./Costs";
import { GradeBoundaries } from "./GradeBoundaries";
import { LearnCardQueue } from "./LearnCardQueue";
import { ReviewQueue } from "./ReviewQueue";
import { StudentPasswords } from "./StudentPasswords";

/** Admin home: things to confirm, review queues, AI spend and imported specs. */
export function AdminPage({ user }: { user: UserOut }) {
  return (
    <AppShell user={user}>
      <h1 className="text-2xl font-bold text-slate-900">Admin</h1>
      <Section title="Needs your attention">
        <AttentionList />
      </Section>
      <Section title="Student passwords">
        <StudentPasswords />
      </Section>
      <Section title="Review queue">
        <ReviewQueue />
      </Section>
      <Section title="Learn cards to review">
        <LearnCardQueue />
      </Section>
      <Section title="AI spend">
        <Costs />
      </Section>
      <Section title="Grade boundaries">
        <GradeBoundaries />
      </Section>
      <Section title="Imported specifications">
        <SpecificationTable />
      </Section>
    </AppShell>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-xl font-semibold text-slate-900">{title}</h2>
      {children}
    </section>
  );
}

function SpecificationTable() {
  const specs = useListSpecifications();
  if (specs.isPending) return <p role="status">Loading…</p>;
  if (specs.isError) return <p role="alert">Couldn&apos;t load specifications.</p>;
  if (specs.data.length === 0) {
    return <p className="text-slate-700">None yet. Add files to curriculum/specs.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-xl bg-surface shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-100">
          <tr>
            <th className="p-2">Subject</th>
            <th className="p-2">Board</th>
            <th className="p-2">Spec</th>
            <th className="p-2">Version</th>
            <th className="p-2 text-right">Topics</th>
            <th className="p-2 text-right">Statements</th>
          </tr>
        </thead>
        <tbody>
          {specs.data.map((spec) => (
            <tr key={spec.id} className="border-t border-slate-100">
              <td className="p-2">{spec.subjectName}</td>
              <td className="p-2">{spec.boardName}</td>
              <td className="p-2">{spec.code}</td>
              <td className="p-2">
                {spec.version}
                {spec.isCurrent ? "" : " (old)"}
              </td>
              <td className="p-2 text-right">{spec.topicCount}</td>
              <td className="p-2 text-right">{spec.objectiveCount}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
