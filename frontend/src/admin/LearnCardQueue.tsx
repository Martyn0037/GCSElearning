// frontend/src/admin/LearnCardQueue.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  decideLearnCard,
  getLearnCardQueueQueryKey,
  useLearnCardQueue,
} from "../api/generated/endpoints";
import { MathText } from "../practice/MathText";

/** Learn cards waiting for review (strict mode). */
export function LearnCardQueue() {
  const queue = useLearnCardQueue();
  const queryClient = useQueryClient();
  const decide = useMutation({
    mutationFn: (vars: { id: string; action: "approve" | "reject" }) =>
      decideLearnCard(vars.id, { action: vars.action }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: getLearnCardQueueQueryKey() }),
  });
  if (queue.isPending) return <p role="status">Loading…</p>;
  if (queue.isError) return <p role="alert">Couldn&apos;t load learn cards.</p>;
  if (queue.data.length === 0) return <p className="text-slate-700">No learn cards waiting.</p>;
  return (
    <ul className="space-y-3">
      {queue.data.map((card) => (
        <li key={card.id} className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
          <p className="text-sm text-slate-600">
            {card.objectiveRef}: <MathText text={card.objectiveText} />
          </p>
          <p>
            <MathText text={card.explanation} />
          </p>
          <p className="text-sm">
            <MathText text={card.workedExample} />
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={decide.isPending}
              onClick={() => {
                decide.mutate({ id: card.id, action: "approve" });
              }}
              className="min-h-11 rounded-lg bg-green-700 px-4 font-semibold text-white disabled:opacity-60"
            >
              Approve
            </button>
            <button
              type="button"
              disabled={decide.isPending}
              onClick={() => {
                decide.mutate({ id: card.id, action: "reject" });
              }}
              className="min-h-11 rounded-lg bg-slate-700 px-4 font-semibold text-white disabled:opacity-60"
            >
              Reject
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
