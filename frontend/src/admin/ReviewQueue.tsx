// frontend/src/admin/ReviewQueue.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { decideQuestion, getReviewQueueQueryKey, useReviewQueue } from "../api/generated/endpoints";
import type { ReviewDecision, ReviewQuestionOut } from "../api/generated/model";

type ReviewDecisionAction = ReviewDecision["action"];
import { MathText } from "../practice/MathText";

type Filter = "all" | "pending_review" | "flagged";

/** Questions waiting for the admin: new ones in strict mode and ones the student flagged. */
export function ReviewQueue() {
  const [filter, setFilter] = useState<Filter>("all");
  const params = filter === "all" ? {} : { status: filter };
  const queue = useReviewQueue(params);
  const queryClient = useQueryClient();
  const decide = useMutation({
    mutationFn: (vars: { id: string; action: ReviewDecisionAction }) =>
      decideQuestion(vars.id, { action: vars.action }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: getReviewQueueQueryKey() }),
  });

  return (
    <div className="space-y-3">
      <div role="group" aria-label="Show" className="flex gap-2">
        {(["all", "pending_review", "flagged"] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => {
              setFilter(value);
            }}
            className={`min-h-11 rounded-full px-3 text-sm ${filter === value ? "bg-brand-700 text-white" : "bg-slate-200 text-slate-800"}`}
          >
            {{ all: "All", pending_review: "New", flagged: "Flagged" }[value]}
          </button>
        ))}
      </div>
      {queue.isPending && <p role="status">Loading…</p>}
      {queue.isError && <p role="alert">Couldn&apos;t load the review queue.</p>}
      {queue.isSuccess && queue.data.items.length === 0 && (
        <p className="text-slate-700">Nothing waiting for review.</p>
      )}
      {decide.isError && (
        <p role="alert">Couldn&apos;t save that decision. Refresh and try again.</p>
      )}
      <ul className="space-y-3">
        {queue.data?.items.map((question) => (
          <ReviewItem
            key={question.id}
            question={question}
            pending={decide.isPending}
            onDecide={(action) => {
              decide.mutate({ id: question.id, action });
            }}
          />
        ))}
      </ul>
    </div>
  );
}

function ReviewItem({
  question,
  pending,
  onDecide,
}: {
  question: ReviewQuestionOut;
  pending: boolean;
  onDecide: (action: ReviewDecisionAction) => void;
}) {
  return (
    <li className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-600">
        {question.subjectName} · {question.objectiveRef} · level {question.difficulty} ·{" "}
        {question.questionType} · confidence {Math.round(question.confidence * 100)}%
        {question.status === "flagged" && (
          <span className="ml-2 rounded-full bg-red-100 px-2 text-red-900">Flagged</span>
        )}
      </p>
      <p className="text-sm text-slate-700">
        <MathText text={question.objectiveText} />
      </p>
      <p className="font-medium text-slate-900">
        <MathText text={question.stem} />
      </p>
      {question.options.length > 0 && (
        <ul className="text-slate-800">
          {question.options.map((option) => (
            <li key={option.label}>
              {option.label}. <MathText text={option.text ?? ""} />
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary className="min-h-11 cursor-pointer text-sm font-medium">
          Key, solution and hints
        </summary>
        <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">
          {JSON.stringify(question.answer, null, 2)}
        </pre>
        <p className="mt-1 text-sm">
          <MathText text={question.workedSolution} />
        </p>
        <ol className="mt-1 list-decimal pl-5 text-sm">
          {question.hints.map((hint, i) => (
            <li key={i}>
              <MathText text={hint} />
            </li>
          ))}
        </ol>
        {question.verificationNotes && (
          <p className="mt-1 text-xs text-slate-600">Verifier: {question.verificationNotes}</p>
        )}
      </details>
      {question.flags.map((flag, i) => (
        <p key={i} className="rounded bg-red-50 p-2 text-sm text-red-900">
          Student reported: {flag.reason ?? "(no reason given)"}
        </p>
      ))}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            onDecide("approve");
          }}
          className="min-h-11 rounded-lg bg-green-700 px-4 font-semibold text-white disabled:opacity-60"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            onDecide("reject");
          }}
          className="min-h-11 rounded-lg bg-slate-700 px-4 font-semibold text-white disabled:opacity-60"
        >
          Reject
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            onDecide("retire");
          }}
          className="min-h-11 rounded-lg border border-slate-300 px-4 disabled:opacity-60"
        >
          Retire
        </button>
      </div>
    </li>
  );
}
