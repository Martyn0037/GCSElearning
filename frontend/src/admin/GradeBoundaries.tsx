// frontend/src/admin/GradeBoundaries.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  getListGradeBoundariesQueryKey,
  replaceGradeBoundaries,
  useListGradeBoundaries,
  useListSpecifications,
} from "../api/generated/endpoints";
import type { GradeBoundariesIn } from "../api/generated/model";

type Tier = GradeBoundariesIn["tier"];
import { ApiError } from "../api/http";

const GRADES: Record<string, number[]> = {
  foundation: [1, 2, 3, 4, 5],
  higher: [3, 4, 5, 6, 7, 8, 9],
  untiered: [1, 2, 3, 4, 5, 6, 7, 8, 9],
};

/**
 * Minimum percentage per grade for a spec and tier, used only to estimate a
 * grade band after boss battles. Leave a grade empty to skip it.
 */
export function GradeBoundaries() {
  const specs = useListSpecifications();
  const [specId, setSpecId] = useState("");
  const spec = specs.data?.find((s) => s.id === specId) ?? specs.data?.[0];
  if (specs.isPending) return <p role="status">Loading…</p>;
  if (specs.isError || !spec) return <p className="text-slate-700">No specifications yet.</p>;
  return (
    <div className="space-y-3">
      <label className="block font-medium">
        Specification
        <select
          value={spec.id}
          onChange={(e) => {
            setSpecId(e.target.value);
          }}
          className="mt-1 block min-h-11 w-full rounded-lg border border-slate-300 px-3"
        >
          {specs.data.map((s) => (
            <option key={s.id} value={s.id}>
              {s.subjectName} · {s.boardName} {s.code}
            </option>
          ))}
        </select>
      </label>
      {(spec.tiered ? (["foundation", "higher"] as const) : ([null] as const)).map((tier) => (
        <TierForm key={`${spec.id}-${tier ?? "untiered"}`} specId={spec.id} tier={tier} />
      ))}
    </div>
  );
}

function TierForm({ specId, tier }: { specId: string; tier: Tier }) {
  const saved = useListGradeBoundaries(specId);
  const queryClient = useQueryClient();
  const id = useId();
  const current = saved.data?.find((b) => b.tier === tier)?.boundaries ?? [];
  const [values, setValues] = useState<Record<number, string> | null>(null);
  const shown = values ?? Object.fromEntries(current.map((b) => [b.grade, String(b.minPercent)]));
  const save = useMutation({
    mutationFn: () =>
      replaceGradeBoundaries(specId, {
        tier,
        boundaries: Object.entries(shown)
          .filter(([, v]) => v.trim() !== "")
          .map(([grade, v]) => ({ grade: Number(grade), minPercent: Number(v) })),
      }),
    onSuccess: () => {
      setValues(null);
      return queryClient.invalidateQueries({ queryKey: getListGradeBoundariesQueryKey(specId) });
    },
  });
  const grades = GRADES[tier ?? "untiered"] ?? [];
  return (
    <form
      aria-labelledby={id}
      className="rounded-xl bg-white p-4 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <h3 id={id} className="font-semibold">
        {tier ? `${tier.charAt(0).toUpperCase()}${tier.slice(1)} tier` : "All students"}
      </h3>
      <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
        {grades.map((grade) => (
          <label key={grade} className="text-sm">
            Grade {grade} from (%)
            <input
              inputMode="decimal"
              value={shown[grade] ?? ""}
              onChange={(e) => {
                setValues({ ...shown, [grade]: e.target.value });
              }}
              className="mt-1 block min-h-11 w-full rounded-lg border border-slate-300 px-2"
            />
          </label>
        ))}
      </div>
      {save.isError && (
        <p role="alert" className="mt-2 text-red-800">
          {save.error instanceof ApiError ? save.error.message : "Couldn't save."}
        </p>
      )}
      {save.isSuccess && (
        <p role="status" className="mt-2 text-green-800">
          Saved.
        </p>
      )}
      <button
        type="submit"
        disabled={save.isPending}
        className="mt-3 min-h-11 rounded-lg bg-brand-700 px-4 font-semibold text-white disabled:opacity-60"
      >
        Save boundaries
      </button>
    </form>
  );
}
