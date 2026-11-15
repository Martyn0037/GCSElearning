// frontend/src/practice/LearnPanel.tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getGetLearnCardQueryKey, getLearnCard } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { MathText } from "./MathText";

const MESSAGES: Record<string, string> = {
  LEARN_PREPARING: "We're writing a learn card for this skill. Have another look in a minute.",
  LEARN_UNAVAILABLE: "Learn cards aren't available yet.",
};

/** "Learn this skill": a short explanation and worked example, fetched when opened. */
export function LearnPanel({ itemId }: { itemId: string }) {
  const [open, setOpen] = useState(false);
  const card = useQuery({
    queryKey: getGetLearnCardQueryKey(itemId),
    queryFn: ({ signal }) => getLearnCard(itemId, { signal }),
    enabled: open,
    retry: false,
  });
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        className="min-h-11 rounded-lg border border-slate-300 px-4 font-medium text-slate-800 hover:bg-slate-50"
      >
        <span aria-hidden="true">📖 </span>Learn this skill
      </button>
    );
  }
  return (
    <section
      aria-label="Learn this skill"
      className="space-y-2 rounded-lg bg-brand-50 p-3 text-slate-800"
    >
      <h3 className="font-semibold text-slate-900">Learn this skill</h3>
      {card.isPending && <p role="status">Loading…</p>}
      {card.isError && (
        <p role="status">
          {card.error instanceof ApiError
            ? (MESSAGES[card.error.code] ?? card.error.message)
            : "Couldn't load the learn card."}
        </p>
      )}
      {card.isSuccess && (
        <>
          <p className="text-sm text-slate-600">
            {card.data.objectiveRef}: <MathText text={card.data.objectiveText} />
          </p>
          <p className="whitespace-pre-line">
            <MathText text={card.data.explanation} />
          </p>
          <h4 className="font-semibold">Worked example</h4>
          <p className="whitespace-pre-line">
            <MathText text={card.data.workedExample} />
          </p>
        </>
      )}
    </section>
  );
}
