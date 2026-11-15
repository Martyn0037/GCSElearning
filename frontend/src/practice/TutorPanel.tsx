// frontend/src/practice/TutorPanel.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { askTutor, getGetTutorThreadQueryKey, getTutorThread } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { MathText } from "./MathText";

const ERRORS: Record<string, string> = {
  TUTOR_LIMIT:
    "That's the most messages for this question. Try the hints, or move on and come back.",
  TUTOR_UNAVAILABLE: "The tutor isn't available right now. Try the hints instead.",
  RATE_LIMITED: "That's a lot of messages. Take a moment, then try again.",
};

/**
 * "Ask about this question": a short conversation with the tutor, limited to
 * this question. Closed until opened, so no request is made unless used.
 */
export function TutorPanel({ itemId }: { itemId: string }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const queryClient = useQueryClient();
  const thread = useQuery({
    queryKey: getGetTutorThreadQueryKey(itemId),
    queryFn: ({ signal }) => getTutorThread(itemId, { signal }),
    enabled: open,
  });
  const ask = useMutation({
    mutationFn: (message: string) => askTutor(itemId, { message }),
    onSuccess: (data) => {
      queryClient.setQueryData(getGetTutorThreadQueryKey(itemId), data);
      setDraft("");
    },
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
        <span aria-hidden="true">💬 </span>Ask about this question
      </button>
    );
  }
  const remaining = thread.data?.remaining;
  const error =
    ask.error instanceof ApiError
      ? (ERRORS[ask.error.code] ?? ask.error.message)
      : ask.isError
        ? "Couldn't send that. Please try again."
        : null;
  return (
    <section
      aria-label="Ask about this question"
      className="space-y-3 rounded-lg border border-slate-200 p-3"
    >
      <h3 className="font-semibold text-slate-900">Ask about this question</h3>
      <p className="text-sm text-slate-600">
        The tutor helps you think it through. It won&apos;t just give you the answer.
      </p>
      {thread.isPending && <p role="status">Loading…</p>}
      <ol className="space-y-2" aria-live="polite">
        {thread.data?.messages.map((message) => (
          <li
            key={message.id}
            className={`rounded-lg p-2 ${message.role === "student" ? "ml-8 bg-brand-50" : "mr-8 bg-slate-100"}`}
          >
            <span className="sr-only">{message.role === "student" ? "You: " : "Tutor: "}</span>
            <MathText text={message.content} />
          </li>
        ))}
      </ol>
      {ask.isPending && (
        <p role="status" className="text-slate-600">
          The tutor is thinking…
        </p>
      )}
      {error && (
        <p role="alert" className="text-amber-900">
          {error}
        </p>
      )}
      {remaining !== 0 && (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) ask.mutate(draft.trim());
          }}
        >
          <label htmlFor={inputId} className="sr-only">
            Your question for the tutor
          </label>
          <input
            id={inputId}
            value={draft}
            maxLength={500}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            placeholder="e.g. Where do I start?"
            className="min-h-11 flex-1 rounded-lg border border-slate-300 px-3"
          />
          <button
            type="submit"
            disabled={ask.isPending || !draft.trim()}
            className="min-h-11 rounded-lg bg-slate-800 px-4 font-semibold text-white disabled:opacity-60"
          >
            Send
          </button>
        </form>
      )}
      {remaining != null && (
        <p className="text-xs text-slate-600">
          {remaining} {remaining === 1 ? "message" : "messages"} left for this question
        </p>
      )}
    </section>
  );
}
