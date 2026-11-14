// frontend/src/subjects/StudentHomePage.tsx
import { Link, Navigate } from "react-router";

import { useGetMySubjects } from "../api/generated/endpoints";
import type { EnrolmentOut, UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";

/** Student home: their subjects. Sends first-time students to setup. */
export function StudentHomePage({ user }: { user: UserOut }) {
  const mine = useGetMySubjects({ query: { enabled: user.setupCompleted } });

  if (!user.setupCompleted) return <Navigate to="/setup" replace />;

  return (
    <AppShell user={user}>
      <h1 className="text-2xl font-bold text-slate-900">Hi {user.displayName}!</h1>
      <h2 className="mt-6 mb-2 text-lg font-semibold text-slate-800">Your subjects</h2>
      {mine.isPending && <p role="status">Loading…</p>}
      {mine.isError && <p role="alert">Couldn&apos;t load your subjects. Please refresh.</p>}
      {mine.isSuccess && (
        <ul className="space-y-2">
          {mine.data.subjects.map((subject) => (
            <li key={subject.id}>
              <SubjectRow subject={subject} />
            </li>
          ))}
        </ul>
      )}
      <Link
        to="/setup"
        className="mt-6 inline-flex min-h-11 items-center text-brand-700 underline underline-offset-4"
      >
        Change my subjects
      </Link>
    </AppShell>
  );
}

function SubjectRow({ subject }: { subject: EnrolmentOut }) {
  const detail = [subject.boardName, subject.tier && capitalise(subject.tier)]
    .filter(Boolean)
    .join(" · ");
  const content = (
    <>
      <span className="flex flex-col">
        <span className="text-lg font-semibold text-slate-900">{subject.subjectName}</span>
        {detail && <span className="text-sm text-slate-600">{detail}</span>}
      </span>
      {subject.status === "active" ? (
        <span aria-hidden="true" className="text-2xl text-brand-700">
          ›
        </span>
      ) : (
        <span className="rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-900">
          Being set up
        </span>
      )}
    </>
  );
  const rowClass = "flex min-h-16 items-center justify-between rounded-xl bg-white p-4 shadow-sm";

  return subject.status === "active" ? (
    <Link
      to={`/subjects/${subject.id}`}
      className={`${rowClass} hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-700`}
    >
      {content}
    </Link>
  ) : (
    <div className={rowClass}>{content}</div>
  );
}

function capitalise(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
