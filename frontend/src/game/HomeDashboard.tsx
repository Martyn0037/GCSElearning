// frontend/src/game/HomeDashboard.tsx
import { Link } from "react-router";

import { useMyDashboard } from "../api/generated/endpoints";
import type { DashboardOut } from "../api/generated/model";
import { continuePath } from "./continuePath";
import { useSoundSetting } from "./sound";

/**
 * The top of the student's home screen: one big Continue button (the next
 * best thing, so he's answering within two taps of logging in), level and
 * XP, streak, today's challenge, and badges.
 */
export function HomeDashboard() {
  // Always refetch on arrival: XP, streak and today's challenge change on other pages.
  const query = useMyDashboard({ query: { refetchOnMount: "always" } });
  if (query.isPending) return <p role="status">Loading…</p>;
  if (query.isError) return null; // the subjects list below still works
  return <Dashboard data={query.data} />;
}

function Dashboard({ data }: { data: DashboardOut }) {
  const path = continuePath(data.continueTo);
  const { level, streak } = data;
  const progress = level.xpForLevel ? level.xpIntoLevel / level.xpForLevel : 1;
  return (
    <div className="mt-4 space-y-4">
      {path ? (
        <Link
          to={path}
          className="flex min-h-16 items-center justify-between rounded-xl bg-brand-700 p-4 text-lg font-semibold text-white hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
        >
          <span>
            <span className="block text-sm font-normal opacity-90">Continue</span>
            {data.continueTo.label}
          </span>
          <span aria-hidden="true">›</span>
        </Link>
      ) : (
        <p className="rounded-xl bg-white p-4 text-slate-700 shadow-sm">
          {data.continueTo.label}. Choose your subjects to get started.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <section aria-label="Level" className="rounded-xl bg-white p-3 shadow-sm">
          <p className="text-sm text-slate-600">Level</p>
          <p className="text-2xl font-bold text-slate-900">{level.level}</p>
          <div
            role="progressbar"
            aria-label="XP to next level"
            aria-valuemin={0}
            aria-valuemax={level.xpForLevel}
            aria-valuenow={level.xpIntoLevel}
            className="mt-2 h-2 rounded-full bg-slate-200"
          >
            <div
              className="h-2 rounded-full bg-brand-600"
              style={{ width: `${String(Math.round(progress * 100))}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-600">
            {level.xpForLevel
              ? `${String(level.xpForLevel - level.xpIntoLevel)} XP to level ${String(level.level + 1)}`
              : "Top level!"}
          </p>
        </section>
        <section aria-label="Streak" className="rounded-xl bg-white p-3 shadow-sm">
          <p className="text-sm text-slate-600">Streak</p>
          <p className="text-2xl font-bold text-slate-900">
            <span aria-hidden="true">🔥 </span>
            {streak.currentDays} {streak.currentDays === 1 ? "day" : "days"}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {streak.activeToday ? "Done for today" : "Answer one question to keep it going"}
            {streak.freezeAvailable ? " · freeze ready" : ""}
          </p>
        </section>
      </div>

      <DailyCard daily={data.daily} />

      <p className="text-sm text-slate-600">
        This week: {data.xpThisWeek} XP · last week: {data.xpLastWeek} XP
      </p>
      <div className="flex flex-wrap items-center gap-x-6">
        <Link
          to="/badges"
          className="inline-flex min-h-11 items-center text-brand-700 underline underline-offset-4"
        >
          Badges ({data.badgesEarned} of {data.badgesTotal})
        </Link>
        <SoundToggle />
      </div>
    </div>
  );
}

function DailyCard({ daily }: { daily: DashboardOut["daily"] }) {
  if (daily.status === "completed") {
    return (
      <p className="rounded-xl bg-green-50 p-4 text-green-900">
        <span aria-hidden="true">✓ </span>Today&apos;s challenge done. Come back tomorrow for a new
        one.
      </p>
    );
  }
  return (
    <Link
      to="/daily"
      className="flex min-h-14 items-center justify-between rounded-xl border-2 border-brand-700 bg-white p-4 font-semibold text-brand-800 hover:bg-brand-50"
    >
      <span>
        Daily challenge
        <span className="block text-sm font-normal text-slate-600">
          {daily.status === "active"
            ? `${String(daily.answered)} of ${String(daily.total)} done`
            : "5 questions on your weak spots · +50 XP"}
        </span>
      </span>
      <span aria-hidden="true">›</span>
    </Link>
  );
}

function SoundToggle() {
  const [on, setOn] = useSoundSetting();
  return (
    <label className="inline-flex min-h-11 items-center gap-2 text-slate-700">
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => {
          setOn(e.target.checked);
        }}
        className="size-5"
      />
      Sounds
    </label>
  );
}
