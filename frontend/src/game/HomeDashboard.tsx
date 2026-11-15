// frontend/src/game/HomeDashboard.tsx
import { Link } from "react-router";

import { useMyDashboard } from "../api/generated/endpoints";
import type { DashboardOut } from "../api/generated/model";
import { Icon } from "../components/Icon";
import { Skeleton } from "../components/ui";
import { cardClass } from "../components/styles";
import { continuePath } from "./continuePath";

/**
 * The top of the student's home screen: one big Continue button (the next
 * best thing, so he's answering within two taps of logging in), level and
 * XP, streak, today's challenge, and badges.
 */
export function HomeDashboard() {
  // Always refetch on arrival: XP, streak and today's challenge change on other pages.
  const query = useMyDashboard({ query: { refetchOnMount: "always" } });
  if (query.isPending) return <DashboardSkeleton />;
  if (query.isError) return null; // the subjects list below still works
  return <Dashboard data={query.data} />;
}

function DashboardSkeleton() {
  return (
    <div role="status" aria-busy="true" className="space-y-3">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-24 w-full rounded-2xl" />
      <div className="grid grid-cols-2 gap-3">
        <Skeleton className="h-28 rounded-2xl" />
        <Skeleton className="h-28 rounded-2xl" />
      </div>
    </div>
  );
}

function Dashboard({ data }: { data: DashboardOut }) {
  const path = continuePath(data.continueTo);
  return (
    <div className="space-y-3">
      {path ? (
        <Link
          to={path}
          className="group relative flex min-h-24 items-center justify-between overflow-hidden rounded-2xl bg-gradient-to-br from-brand-500 via-brand-600 to-brand-800 p-5 text-white shadow-brand transition-transform active:scale-[0.99] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 -right-8 size-36 rounded-full bg-white/10"
          />
          <span className="relative">
            <span className="block text-xs font-semibold tracking-wider text-white/80 uppercase">
              Continue
            </span>
            <span className="mt-1 block text-xl font-bold">{data.continueTo.label}</span>
          </span>
          <span className="relative grid size-11 place-items-center rounded-full bg-white/15 transition-transform group-hover:translate-x-0.5">
            <Icon name="chevronRight" />
          </span>
        </Link>
      ) : (
        <p className={`${cardClass} p-5 text-slate-700`}>
          {data.continueTo.label}. Choose your subjects to get started.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <LevelTile level={data.level} />
        <StreakTile streak={data.streak} />
      </div>

      <DailyCard daily={data.daily} />

      <div className="grid grid-cols-2 gap-3">
        <section aria-label="XP this week" className={`${cardClass} p-4`}>
          <p className="text-xs font-medium text-slate-600">This week</p>
          <p className="mt-1 text-2xl font-bold text-slate-900 tabular-nums">
            {data.xpThisWeek} <span className="text-sm font-semibold text-xp">XP</span>
          </p>
          <p className="sr-only">
            This week: {data.xpThisWeek} XP · last week: {data.xpLastWeek} XP
          </p>
          <p aria-hidden="true" className="mt-1 text-xs text-slate-600">
            Last week {data.xpLastWeek} XP
          </p>
        </section>
        <Link
          to="/badges"
          aria-label={`Badges (${String(data.badgesEarned)} of ${String(data.badgesTotal)})`}
          className={`${cardClass} flex flex-col justify-between p-4 transition hover:shadow-raised focus-visible:outline-2 focus-visible:outline-brand-600`}
        >
          <span className="flex items-center justify-between text-xs font-medium text-slate-600">
            Badges
            <Icon name="trophy" className="size-4 text-xp" />
          </span>
          <span className="mt-1 text-2xl font-bold text-slate-900 tabular-nums">
            {data.badgesEarned}
            <span className="text-sm font-semibold text-slate-500"> / {data.badgesTotal}</span>
          </span>
          <span className="mt-1 text-xs font-medium text-brand-ink">See all</span>
        </Link>
      </div>
    </div>
  );
}

function LevelTile({ level }: { level: DashboardOut["level"] }) {
  const progress = level.xpForLevel ? level.xpIntoLevel / level.xpForLevel : 1;
  return (
    <section aria-label="Level" className={`${cardClass} p-4`}>
      <p className="text-xs font-medium text-slate-600">Level</p>
      <p className="mt-1 text-3xl font-bold text-slate-900 tabular-nums">{level.level}</p>
      <div
        role="progressbar"
        aria-label="XP to next level"
        aria-valuemin={0}
        aria-valuemax={level.xpForLevel}
        aria-valuenow={level.xpIntoLevel}
        className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-700 transition-[width] duration-700"
          style={{ width: `${String(Math.round(progress * 100))}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-slate-600">
        {level.xpForLevel
          ? `${String(level.xpForLevel - level.xpIntoLevel)} XP to level ${String(level.level + 1)}`
          : "Top level!"}
      </p>
    </section>
  );
}

function StreakTile({ streak }: { streak: DashboardOut["streak"] }) {
  return (
    <section aria-label="Streak" className={`${cardClass} p-4`}>
      <p className="text-xs font-medium text-slate-600">Streak</p>
      <p className="mt-1 flex items-center gap-1.5 text-3xl font-bold text-slate-900 tabular-nums">
        <Icon
          name="flame"
          className={`size-7 ${streak.activeToday ? "fill-orange-400 text-orange-500" : "text-slate-400"}`}
        />
        <span>{`${String(streak.currentDays)} ${streak.currentDays === 1 ? "day" : "days"}`}</span>
      </p>
      <p className="mt-1.5 text-xs text-slate-600">
        {streak.activeToday ? "Done for today" : "Answer one question to keep it going"}
        {streak.freezeAvailable ? " · freeze ready" : ""}
      </p>
    </section>
  );
}

function DailyCard({ daily }: { daily: DashboardOut["daily"] }) {
  if (daily.status === "completed") {
    return (
      <p className="flex items-center gap-3 rounded-2xl bg-green-50 p-4 text-green-900">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-green-100">
          <Icon name="check" />
        </span>
        <span>Today&apos;s challenge done. Come back tomorrow for a new one.</span>
      </p>
    );
  }
  const total = daily.total || 5;
  return (
    <Link
      to="/daily"
      className={`${cardClass} flex min-h-16 items-center gap-3 p-4 transition hover:shadow-raised focus-visible:outline-2 focus-visible:outline-brand-600`}
    >
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-900">
        <Icon name="bolt" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-slate-900">Daily challenge</span>
        <span className="block text-sm text-slate-600">
          {daily.status === "active"
            ? `${String(daily.answered)} of ${String(daily.total)} done`
            : "5 questions on your weak spots · +50 XP"}
        </span>
        {daily.status === "active" && (
          <span aria-hidden="true" className="mt-2 flex gap-1">
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                className={`h-1.5 flex-1 rounded-full ${i < daily.answered ? "bg-amber-500" : "bg-slate-200"}`}
              />
            ))}
          </span>
        )}
      </span>
      <Icon name="chevronRight" className="size-5 text-slate-400" />
    </Link>
  );
}
