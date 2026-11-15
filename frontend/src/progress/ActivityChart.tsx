// frontend/src/progress/ActivityChart.tsx
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DailyActivity } from "../api/generated/model";

// Categorical slots 1 and 2 of the reference palette (validated on the light
// surface: CVD ΔE 24.7, normal-vision ΔE 33.6, contrast ≥ 3:1).
const COLOURS = { right: "#2a78d6", notRight: "#eb6834" } as const;
// Theme-aware: these CSS variables are remapped in dark mode.
const INK = { axis: "var(--color-slate-600)", grid: "var(--color-slate-200)" };

interface Row {
  label: string;
  right: number;
  notRight: number;
}

function toRows(daily: readonly DailyActivity[]): Row[] {
  return daily.map((d) => ({
    label: new Date(`${d.date}T12:00:00`).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
    }),
    right: d.correct,
    notRight: d.attempts - d.correct,
  }));
}

/**
 * Answers per day for 30 days, split into right / not right (stacked).
 * One y-axis (counts), legend, hover tooltip, plus a table for screen readers
 * and anyone who prefers numbers.
 */
export function ActivityChart({ daily }: { daily: readonly DailyActivity[] }) {
  const rows = toRows(daily);
  const total = daily.reduce((sum, d) => sum + d.attempts, 0);
  if (total === 0) {
    return <p className="text-slate-700">No answers in the last 30 days yet.</p>;
  }
  return (
    <figure className="space-y-2">
      <div className="h-56 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            margin={{ top: 8, right: 4, bottom: 0, left: -24 }}
            barCategoryGap={2}
          >
            <CartesianGrid vertical={false} stroke={INK.grid} />
            <XAxis
              dataKey="label"
              tick={{ fill: INK.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: INK.grid }}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fill: INK.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              contentStyle={{
                borderRadius: 12,
                borderColor: INK.grid,
                background: "var(--color-surface)",
                fontSize: 13,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 13, color: INK.axis }} iconType="square" />
            <Bar
              dataKey="right"
              name="Right"
              stackId="day"
              isAnimationActive={false}
              fill={COLOURS.right}
              stroke="var(--color-surface)"
              strokeWidth={1}
            />
            <Bar
              dataKey="notRight"
              name="Not right"
              stackId="day"
              isAnimationActive={false}
              fill={COLOURS.notRight}
              stroke="var(--color-surface)"
              strokeWidth={1}
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="text-sm text-slate-600">
        {total} answers in the last 30 days.
      </figcaption>
      <details className="text-sm">
        <summary className="flex min-h-11 cursor-pointer items-center font-medium text-brand-ink">
          Show as a table
        </summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th className="py-1">Day</th>
              <th className="py-1 text-right">Right</th>
              <th className="py-1 text-right">Not right</th>
            </tr>
          </thead>
          <tbody>
            {rows
              .filter((r) => r.right + r.notRight > 0)
              .map((r) => (
                <tr key={r.label} className="border-t border-slate-100">
                  <td className="py-1">{r.label}</td>
                  <td className="py-1 text-right">{r.right}</td>
                  <td className="py-1 text-right">{r.notRight}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
