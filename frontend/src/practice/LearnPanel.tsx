// frontend/src/practice/LearnPanel.tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getGetLearnCardQueryKey, getLearnCard } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { Icon } from "../components/Icon";
import { buttonClass } from "../components/styles";
import { Skeleton } from "../components/ui";
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
        className={`${buttonClass("secondary", true)} text-slate-800`}
      >
        <Icon name="book" className="size-4 text-brand-ink" />
        Learn this skill
      </button>
    );
  }
  return (
    <section
      aria-label="Learn this skill"
      className="w-full animate-fade-up space-y-3 rounded-2xl bg-surface p-5 text-slate-800 shadow-card"
    >
      <h3 className="flex items-center gap-2 font-semibold text-slate-900">
        <span className="grid size-8 place-items-center rounded-lg bg-brand-50 text-brand-ink">
          <Icon name="book" className="size-4" />
        </span>
        Learn this skill
      </h3>
      {card.isPending && (
        <div role="status" aria-busy="true" className="space-y-2">
          <span className="sr-only">Loading…</span>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}
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
          <p className="leading-relaxed whitespace-pre-line">
            <MathText text={card.data.explanation} />
          </p>
          <h4 className="pt-1 font-semibold text-slate-900">Worked example</h4>
          <p className="rounded-xl bg-slate-50 p-3 leading-relaxed whitespace-pre-line">
            <MathText text={card.data.workedExample} />
          </p>
        </>
      )}
    </section>
  );
}
