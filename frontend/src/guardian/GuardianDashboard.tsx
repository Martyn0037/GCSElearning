// frontend/src/guardian/GuardianDashboard.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, useNavigate } from "react-router";

import {
  deleteStudent,
  exportStudentData,
  getMyStudentsQueryKey,
  giveConsent,
  useMyStudents,
  useStudentWeeklySummary,
  withdrawConsent,
} from "../api/generated/endpoints";
import type { LinkedStudentOut, UserOut, WeeklySummaryOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { MasteryRing } from "../game/Ring";

const dayName = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

/** The guardian's read-only view: consent, the weekly summary, export and deletion. */
export function GuardianDashboard({ user }: { user: UserOut }) {
  const students = useMyStudents();
  const [selected, setSelected] = useState<string | null>(null);
  const student = students.data?.find((s) => s.id === selected) ?? students.data?.[0] ?? null;

  return (
    <AppShell user={user}>
      <h1 className="text-2xl font-bold text-slate-900">Progress dashboard</h1>
      {students.isPending && <p role="status">Loading…</p>}
      {students.isError && <p role="alert">Couldn&apos;t load your students. Please refresh.</p>}
      {students.isSuccess && students.data.length === 0 && (
        <p className="mt-4 text-slate-700">No students are linked to your account yet.</p>
      )}
      {students.isSuccess && students.data.length > 1 && (
        <label className="mt-4 block font-medium">
          Student
          <select
            value={student?.id}
            onChange={(e) => {
              setSelected(e.target.value);
            }}
            className="mt-1 block min-h-11 rounded-lg border border-slate-300 px-3"
          >
            {students.data.map((s) => (
              <option key={s.id} value={s.id}>
                {s.displayName}
              </option>
            ))}
          </select>
        </label>
      )}
      {student && (
        <div key={student.id} className="mt-4 space-y-6">
          <ConsentCard student={student} />
          <Week studentId={student.id} />
          <YourData student={student} />
        </div>
      )}
    </AppShell>
  );
}

function ConsentCard({ student }: { student: LinkedStudentOut }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: getMyStudentsQueryKey() });
  const give = useMutation({
    mutationFn: () => giveConsent(student.id, { policyVersion: student.currentPolicyVersion }),
    onSuccess: refresh,
  });
  const withdraw = useMutation({
    mutationFn: () => withdrawConsent(student.id),
    onSuccess: refresh,
  });
  const { consent } = student;
  if (consent.granted && consent.policyVersion === student.currentPolicyVersion) {
    return (
      <p className="rounded-xl bg-white p-4 text-slate-700 shadow-sm">
        You agreed to the{" "}
        <Link to="/privacy" className="text-brand-700 underline">
          privacy notice
        </Link>{" "}
        for {student.displayName}
        {consent.grantedAt ? ` on ${shortDate.format(new Date(consent.grantedAt))}` : ""}.{" "}
        <button
          type="button"
          onClick={() => {
            withdraw.mutate();
          }}
          disabled={withdraw.isPending}
          className="min-h-11 text-brand-700 underline"
        >
          Withdraw consent
        </button>
      </p>
    );
  }
  return (
    <section aria-label="Consent" className="space-y-2 rounded-xl bg-amber-50 p-4 text-amber-950">
      <p className="font-semibold">Please read and agree to the privacy notice</p>
      <p>
        It explains, in plain language, what GCSE Coach keeps about {student.displayName}, how AI is
        used, and how to download or delete it.
      </p>
      <div className="flex flex-wrap items-center gap-4">
        <Link to="/privacy" className="inline-flex min-h-11 items-center underline">
          Read the privacy notice
        </Link>
        <button
          type="button"
          onClick={() => {
            give.mutate();
          }}
          disabled={give.isPending}
          className="min-h-11 rounded-lg bg-brand-700 px-4 font-semibold text-white disabled:opacity-60"
        >
          I&apos;ve read it and agree
        </button>
      </div>
    </section>
  );
}

function Week({ studentId }: { studentId: string }) {
  const [weeksAgo, setWeeksAgo] = useState(0);
  const summary = useStudentWeeklySummary(studentId, { weeks_ago: weeksAgo });
  return (
    <section aria-label="Weekly summary" className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          disabled={weeksAgo >= 11}
          onClick={() => {
            setWeeksAgo((w) => w + 1);
          }}
          className="min-h-11 px-2 text-brand-700 underline disabled:opacity-40"
        >
          ‹ Earlier
        </button>
        <h2 className="text-lg font-semibold text-slate-900">
          {summary.data
            ? `Week of ${shortDate.format(new Date(summary.data.weekStart))}`
            : "This week"}
        </h2>
        <button
          type="button"
          disabled={weeksAgo === 0}
          onClick={() => {
            setWeeksAgo((w) => w - 1);
          }}
          className="min-h-11 px-2 text-brand-700 underline disabled:opacity-40"
        >
          Later ›
        </button>
      </div>
      {summary.isPending && <p role="status">Loading…</p>}
      {summary.isError && <p role="alert">Couldn&apos;t load this week.</p>}
      {summary.isSuccess && <WeekDetails week={summary.data} />}
    </section>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-3 shadow-sm">
      <p className="text-sm text-slate-600">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function WeekDetails({ week }: { week: WeeklySummaryOut }) {
  const accuracy = week.answered
    ? `${String(Math.round((100 * week.correct) / week.answered))}%`
    : "–";
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(week.weekStart);
    d.setUTCDate(d.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
  const active = new Set(week.activeDays);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Tile label="Questions answered" value={String(week.answered)} />
        <Tile label="Right" value={accuracy} />
        <Tile label="Time practising" value={`${String(week.minutes)} min`} />
        <Tile label="XP earned" value={String(week.xp)} />
        <Tile label="Streak" value={`${String(week.streakDays)} days`} />
        <Tile label="Mistakes fixed" value={String(week.mistakesFixed)} />
      </div>
      <ol
        aria-label="Days practised"
        className="flex justify-between rounded-xl bg-white p-3 shadow-sm"
      >
        {days.map((day) => (
          <li key={day} className="flex flex-col items-center gap-1 text-xs text-slate-600">
            <span
              className={`size-6 rounded-full ${active.has(day) ? "bg-brand-600" : "bg-slate-200"}`}
              aria-hidden="true"
            />
            {dayName.format(new Date(day))}
            <span className="sr-only">{active.has(day) ? "practised" : "no practice"}</span>
          </li>
        ))}
      </ol>
      {week.subjects.map((subject) => (
        <section key={subject.subjectName} className="rounded-xl bg-white p-4 shadow-sm">
          <h3 className="font-semibold text-slate-900">{subject.subjectName}</h3>
          <p className="text-sm text-slate-600">
            {subject.answered} answered this week
            {subject.answered ? `, ${String(subject.correct)} right` : ""}
          </p>
          {subject.weakTopics.length > 0 && (
            <>
              <p className="mt-2 text-sm font-medium text-slate-800">Topics to work on</p>
              <ul className="mt-1 space-y-1">
                {subject.weakTopics.map((topic) => (
                  <li key={topic.title} className="flex items-center justify-between gap-2">
                    <span>{topic.title}</span>
                    <MasteryRing ring={topic.ring} progress={topic.mastery} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      ))}
      {(week.badges.length > 0 || week.bossBattles.length > 0) && (
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h3 className="font-semibold text-slate-900">Achievements</h3>
          <ul className="mt-1 list-disc pl-5 text-slate-800">
            {week.badges.map((badge) => (
              <li key={badge}>Badge: {badge}</li>
            ))}
            {week.bossBattles.map((boss, index) => (
              <li key={index}>
                Boss battle on {boss.topicTitle ?? "a topic"}: {boss.percent ?? 0}%
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

const DELETE_ERRORS: Record<string, string> = {
  WRONG_PASSWORD: "That password isn't right.",
  RATE_LIMITED: "Too many tries. Wait a few minutes.",
};

function YourData({ student }: { student: LinkedStudentOut }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ids = { password: useId(), confirm: useId() };
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const download = useMutation({
    mutationFn: () => exportStudentData(student.id),
    onSuccess: (data: unknown) => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `gcse-coach-${student.displayName}.json`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteStudent(student.id, { confirm: "DELETE", password }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: getMyStudentsQueryKey() });
      void navigate("/guardian", { replace: true });
    },
  });
  return (
    <section aria-label="Your data" className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">{student.displayName}&apos;s data</h2>
      <button
        type="button"
        disabled={download.isPending}
        onClick={() => {
          download.mutate();
        }}
        className="min-h-11 rounded-lg border border-slate-300 px-4 font-medium"
      >
        Download all data (JSON)
      </button>
      {download.isError && <p role="alert">Couldn&apos;t download. Please try again.</p>}
      <details className="rounded-lg border border-red-200 p-3">
        <summary className="min-h-11 cursor-pointer font-medium text-red-800">
          Delete account permanently
        </summary>
        <form
          className="mt-2 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            remove.mutate();
          }}
        >
          <p className="text-sm text-slate-700">
            This deletes {student.displayName}&apos;s account and every answer, mistake and message.
            It can&apos;t be undone. Download the data first if you want a copy.
          </p>
          <label htmlFor={ids.password} className="block text-sm font-medium">
            Your password
          </label>
          <input
            id={ids.password}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            className="block min-h-11 w-full rounded-lg border border-slate-300 px-3"
          />
          <label htmlFor={ids.confirm} className="block text-sm font-medium">
            Type DELETE to confirm
          </label>
          <input
            id={ids.confirm}
            value={confirm}
            onChange={(e) => {
              setConfirm(e.target.value);
            }}
            className="block min-h-11 w-full rounded-lg border border-slate-300 px-3"
          />
          {remove.isError && (
            <p role="alert" className="text-red-800">
              {remove.error instanceof ApiError
                ? (DELETE_ERRORS[remove.error.code] ?? remove.error.message)
                : "Couldn't delete. Please try again."}
            </p>
          )}
          <button
            type="submit"
            disabled={confirm !== "DELETE" || !password || remove.isPending}
            className="min-h-11 rounded-lg bg-red-700 px-4 font-semibold text-white disabled:opacity-50"
          >
            Delete permanently
          </button>
        </form>
      </details>
    </section>
  );
}
