// frontend/src/game/BadgesPage.tsx
import { Link } from "react-router";

import { useMyBadges } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";

const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

/** Every badge: earned ones with their date, the rest with how to earn them. */
export function BadgesPage({ user }: { user: UserOut }) {
  const badges = useMyBadges();
  return (
    <AppShell user={user}>
      <Link to="/" className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ Home
      </Link>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">Badges</h1>
      {badges.isPending && <p role="status">Loading…</p>}
      {badges.isError && <p role="alert">Couldn&apos;t load your badges. Please refresh.</p>}
      {badges.isSuccess && (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {badges.data.map((badge) => (
            <li
              key={badge.code}
              className={`rounded-xl p-4 shadow-sm ${badge.earnedAt ? "bg-amber-50" : "bg-white"}`}
            >
              <p className="font-semibold text-slate-900">
                <span aria-hidden="true">{badge.earnedAt ? "🏅 " : "○ "}</span>
                {badge.name}
              </p>
              <p className="text-sm text-slate-700">{badge.description}</p>
              <p className="mt-1 text-xs text-slate-600">
                {badge.earnedAt
                  ? `Earned ${dateFormat.format(new Date(badge.earnedAt))}`
                  : "Not yet"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
