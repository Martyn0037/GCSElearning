// frontend/src/subjects/StudentHomePage.tsx
import { Link, Navigate } from "react-router";

import { useGetMySubjects } from "../api/generated/endpoints";
import type { EnrolmentOut, UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";
import { Icon } from "../components/Icon";
import { Chip, ErrorNotice, LoadingCards, SectionTitle } from "../components/ui";
import { cardClass } from "../components/styles";
import { HomeDashboard } from "../game/HomeDashboard";
import { subjectAccent } from "./subjectAccent";

const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });

/**
 * Student home: Continue, level, streak, today's challenge, then their
 * subjects. Sends first-time students to setup.
 */
export function StudentHomePage({ user }: { user: UserOut }) {
  const mine = useGetMySubjects({ query: { enabled: user.setupCompleted } });

  if (!user.setupCompleted) return <Navigate to="/setup" replace />;

  return (
    <AppShell user={user}>
      <div className="mb-5">
        <p className="text-sm font-medium text-slate-600">{today.format(new Date())}</p>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Hi {user.displayName}!</h1>
      </div>
      <HomeDashboard />
      <SectionTitle
        action={
          <Link
            to="/setup"
            className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-medium text-brand-ink hover:bg-brand-50"
          >
            Change my subjects
          </Link>
        }
      >
        Your subjects
      </SectionTitle>
      {mine.isPending && <LoadingCards rows={2} />}
      {mine.isError && <ErrorNotice>Couldn&apos;t load your subjects. Please refresh.</ErrorNotice>}
      {mine.isSuccess && (
        <ul className="space-y-2.5">
          {mine.data.subjects.map((subject) => (
            <li key={subject.id}>
              <SubjectRow subject={subject} />
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}

function SubjectRow({ subject }: { subject: EnrolmentOut }) {
  const detail = [subject.boardName, subject.tier && capitalise(subject.tier)]
    .filter(Boolean)
    .join(" · ");
  const accent = subjectAccent(subject.subjectName);
  const content = (
    <>
      <span
        aria-hidden="true"
        className={`grid size-11 shrink-0 place-items-center rounded-xl text-lg font-bold ${accent}`}
      >
        {subject.subjectName.charAt(0)}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-semibold text-slate-900">{subject.subjectName}</span>
        {detail && <span className="truncate text-sm text-slate-600">{detail}</span>}
      </span>
      {subject.status === "active" ? (
        <Icon name="chevronRight" className="size-5 text-slate-400" />
      ) : (
        <Chip tone="warn">Being set up</Chip>
      )}
    </>
  );
  const rowClass = `${cardClass} flex min-h-16 items-center gap-3 p-3.5`;

  return subject.status === "active" ? (
    <Link
      to={`/subjects/${subject.id}`}
      className={`${rowClass} transition hover:shadow-raised focus-visible:outline-2 focus-visible:outline-brand-600`}
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
