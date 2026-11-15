// frontend/src/game/BadgesPage.tsx
import { useMyBadges } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";
import { Icon } from "../components/Icon";
import { cardClass } from "../components/styles";
import { ErrorNotice, LoadingCards, PageHeader } from "../components/ui";

const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

/** Every badge: earned ones with their date, the rest with how to earn them. */
export function BadgesPage({ user }: { user: UserOut }) {
  const badges = useMyBadges();
  const earned = badges.data?.filter((b) => b.earnedAt).length ?? 0;
  const total = badges.data?.length ?? 0;
  return (
    <AppShell user={user}>
      <PageHeader
        title="Badges"
        subtitle={badges.isSuccess ? `${String(earned)} of ${String(total)} earned` : undefined}
      />
      {badges.isSuccess && total > 0 && (
        <div
          aria-hidden="true"
          className="-mt-2 mb-5 h-2 overflow-hidden rounded-full bg-slate-200"
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500"
            style={{ width: `${String(Math.round((earned / total) * 100))}%` }}
          />
        </div>
      )}
      {badges.isPending && <LoadingCards rows={4} />}
      {badges.isError && <ErrorNotice>Couldn&apos;t load your badges. Please refresh.</ErrorNotice>}
      {badges.isSuccess && (
        <ul className="grid grid-cols-2 gap-3">
          {badges.data.map((badge) => (
            <li
              key={badge.code}
              className={`${cardClass} flex flex-col items-center p-4 text-center ${badge.earnedAt ? "" : "opacity-80"}`}
            >
              <span
                aria-hidden="true"
                className={`mb-2 grid size-14 place-items-center rounded-full ${
                  badge.earnedAt
                    ? "bg-gradient-to-br from-amber-300 to-orange-500 text-white shadow-md"
                    : "bg-slate-100 text-slate-400 ring-2 ring-slate-200 ring-dashed"
                }`}
              >
                <Icon name="trophy" className="size-7" />
              </span>
              <p className="leading-tight font-semibold text-slate-900">{badge.name}</p>
              <p className="mt-1 text-xs leading-snug text-slate-600">{badge.description}</p>
              <p
                className={`mt-auto pt-2 text-xs font-semibold ${badge.earnedAt ? "text-xp" : "text-slate-500"}`}
              >
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
