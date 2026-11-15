// frontend/src/admin/Costs.tsx
import { useAiCosts } from "../api/generated/endpoints";

const gbp = (value: string) => `£${value}`;
const day = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

/** Claude spend today and this month against the caps, by purpose, and the last 30 days. */
export function Costs() {
  const costs = useAiCosts();
  if (costs.isPending) return <p role="status">Loading…</p>;
  if (costs.isError) return <p role="alert">Couldn&apos;t load costs.</p>;
  const c = costs.data;
  const monthShare = Number(c.monthGbp) / Number(c.monthlyCapGbp || "1");
  const peak = Math.max(...c.last30Days.map((d) => Number(d.gbp)), 0.01);
  return (
    <div className="space-y-4">
      {!c.apiKeyConfigured && (
        <p className="rounded-lg bg-amber-50 p-3 text-amber-900">
          No Anthropic API key is set, so Claude isn&apos;t being called.
        </p>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-white p-3 shadow-sm">
          <p className="text-sm text-slate-600">Today</p>
          <p className="text-2xl font-bold">{gbp(c.todayGbp)}</p>
          <p className="text-xs text-slate-600">cap {gbp(c.dailyCapGbp)}</p>
        </div>
        <div className="rounded-xl bg-white p-3 shadow-sm">
          <p className="text-sm text-slate-600">This month</p>
          <p className="text-2xl font-bold">{gbp(c.monthGbp)}</p>
          <div
            role="progressbar"
            aria-label="Share of monthly cap used"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(monthShare * 100)}
            className="mt-1 h-2 rounded-full bg-slate-200"
          >
            <div
              className={`h-2 rounded-full ${monthShare > 0.8 ? "bg-red-600" : "bg-brand-600"}`}
              style={{ width: `${String(Math.min(100, Math.round(monthShare * 100)))}%` }}
            />
          </div>
          <p className="text-xs text-slate-600">
            cap {gbp(c.monthlyCapGbp)} · {c.monthCalls} calls · {c.monthFailures} failed
          </p>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <caption className="p-2 text-left font-semibold">This month by purpose</caption>
          <thead className="bg-slate-100">
            <tr>
              <th className="p-2">Purpose</th>
              <th className="p-2">Spend</th>
              <th className="p-2">Calls</th>
              <th className="p-2">Failed</th>
            </tr>
          </thead>
          <tbody>
            {c.byPurpose.map((p) => (
              <tr key={p.purpose} className="border-t border-slate-100">
                <td className="p-2">{p.purpose}</td>
                <td className="p-2">{gbp(p.gbp)}</td>
                <td className="p-2">{p.calls}</td>
                <td className="p-2">{p.failures}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto rounded-xl bg-white p-3 shadow-sm">
        <table className="w-full text-left text-sm">
          <caption className="text-left font-semibold">Last 30 days</caption>
          <tbody>
            {c.last30Days.map((d) => (
              <tr key={d.date}>
                <td className="w-20 py-0.5 pr-2 text-slate-600">{day.format(new Date(d.date))}</td>
                <td className="py-0.5">
                  <div
                    className="h-3 rounded bg-brand-600"
                    style={{
                      width: `${String(Math.max(1, Math.round((100 * Number(d.gbp)) / peak)))}%`,
                    }}
                    aria-hidden="true"
                  />
                </td>
                <td className="w-20 py-0.5 pl-2 text-right">{gbp(d.gbp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
