// frontend/src/practice/TutorPanel.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { askTutor, getGetTutorThreadQueryKey, getTutorThread } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { Icon } from "../components/Icon";
import { buttonClass } from "../components/styles";
import { Button } from "../components/ui";
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
        className={`${buttonClass("secondary", true)} text-slate-800`}
      >
        <Icon name="chat" className="size-4 text-brand-ink" />
        Ask about this question
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
      className="w-full animate-fade-up space-y-3 rounded-2xl bg-surface p-5 shadow-card"
    >
      <h3 className="flex items-center gap-2 font-semibold text-slate-900">
        <span className="grid size-8 place-items-center rounded-lg bg-brand-50 text-brand-ink">
          <Icon name="chat" className="size-4" />
        </span>
        Ask about this question
      </h3>
      <p className="text-sm text-slate-600">
        The tutor helps you think it through. It won&apos;t just give you the answer.
      </p>
      {thread.isPending && (
        <p role="status" className="text-sm text-slate-600">
          Loading…
        </p>
      )}
      <ol className="space-y-2" aria-live="polite">
        {thread.data?.messages.map((message) => (
          <li
            key={message.id}
            className={`animate-fade-up px-3.5 py-2.5 leading-relaxed ${message.role === "student" ? "ml-10 rounded-2xl rounded-br-md bg-brand-600 text-white" : "mr-10 rounded-2xl rounded-bl-md bg-slate-100 text-slate-800"}`}
          >
            <span className="sr-only">{message.role === "student" ? "You: " : "Tutor: "}</span>
            <MathText text={message.content} />
          </li>
        ))}
      </ol>
      {ask.isPending && (
        <p
          role="status"
          className="mr-10 flex w-fit items-center gap-2 rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2.5 text-sm text-slate-600"
        >
          <span className="size-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
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
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-slate-300 bg-surface px-3 text-slate-900 focus:border-brand-600 focus:outline-2 focus:outline-brand-600"
          />
          <Button type="submit" disabled={ask.isPending || !draft.trim()}>
            Send
          </Button>
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
