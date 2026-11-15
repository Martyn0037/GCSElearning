// frontend/src/practice/PracticeSession.tsx
import { useMutation } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import {
  answerPracticeItem,
  similarPracticeItem,
  useFlagPracticeItem,
  useRevealHint,
} from "../api/generated/endpoints";
import type { PracticeItemOut, UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { MathText } from "./MathText";
import { LearnPanel } from "./LearnPanel";
import { QuestionCard } from "./QuestionCard";
import { ResultPanel } from "./ResultPanel";
import { TutorPanel } from "./TutorPanel";

const LOAD_ERRORS: Record<string, string> = {
  MARKING_IN_PROGRESS: "Your answer is still being marked. Try again in a moment.",
  ANSWER_TOO_LONG: "That answer is too long for this question.",
  QUESTIONS_PREPARING: "We're preparing questions for this topic. Try again in a minute.",
  SUBJECT_NOT_READY: "This subject is still being set up.",
};

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return LOAD_ERRORS[error.code] ?? error.message;
  return fallback;
}

interface PracticeSessionProps {
  user: UserOut;
  /** Fetches the next question (topic practice or a review). */
  fetchNext: () => Promise<PracticeItemOut>;
  back: { to: string; label: string };
  /** Shown instead of an error when ``fetchNext`` fails with ``doneCode``. */
  done?: { code: string; content: ReactNode };
}

/**
 * One question at a time: answer, get hints, see the result (with the
 * "where it went wrong" explanation), try a similar one, carry on.
 */
export function PracticeSession({ user, fetchNext, back, done }: PracticeSessionProps) {
  const [served, setServed] = useState<PracticeItemOut | null>(null);
  const next = useMutation({ mutationFn: fetchNext });
  const similar = useMutation({ mutationFn: (itemId: string) => similarPracticeItem(itemId) });
  const hint = useRevealHint();
  const flag = useFlagPracticeItem();
  // The generated hook can't vary headers per call, so wrap the function.
  const answer = useMutation({
    mutationFn: (vars: { itemId: string; answer: string; key: string }) =>
      answerPracticeItem(
        vars.itemId,
        { answer: vars.answer },
        { headers: { "Idempotency-Key": vars.key } },
      ),
  });
  // One idempotency key per item, reused if the answer request is retried.
  const keys = useRef(new Map<string, string>());

  const { mutate: requestNext } = next;
  const { reset: resetAnswer } = answer;
  const loadNext = useCallback(() => {
    resetAnswer();
    requestNext(undefined, { onSuccess: setServed });
  }, [requestNext, resetAnswer]);

  useEffect(() => {
    loadNext();
  }, [loadNext]);

  const item = served;
  const result = answer.data && answer.data.itemId === item?.id ? answer.data : null;

  function submit(value: string) {
    if (!item) return;
    const key = keys.current.get(item.id) ?? crypto.randomUUID();
    keys.current.set(item.id, key);
    answer.mutate({ itemId: item.id, answer: value, key });
  }

  function trySimilar() {
    if (!item) return;
    similar.mutate(item.id, {
      onSuccess: (loaded) => {
        resetAnswer();
        setServed(loaded);
      },
    });
  }

  function sendFlag(reason: string) {
    if (!item) return;
    flag.mutate({ itemId: item.id, data: reason ? { reason } : {} }, { onSuccess: loadNext });
  }

  const finished = done && next.error instanceof ApiError && next.error.code === done.code;

  return (
    <AppShell user={user}>
      <Link to={back.to} className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ {back.label}
      </Link>

      {next.isPending && (
        <p role="status" className="mt-6 text-slate-700">
          Getting your next question…
        </p>
      )}
      {finished && <div className="mt-6">{done.content}</div>}
      {next.isError && !finished && (
        <div role="alert" className="mt-6 space-y-3 rounded-xl bg-amber-50 p-4 text-amber-900">
          <p>{errorMessage(next.error, "Couldn't load a question. Please try again.")}</p>
          <button type="button" onClick={loadNext} className="min-h-11 font-semibold underline">
            Try again
          </button>
        </div>
      )}

      {item && next.isSuccess && (
        <div className="mt-4 space-y-4 rounded-2xl bg-white p-4 shadow-sm">
          {item.review && !result && (
            <p className="inline-block rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-900">
              Review: you got this one wrong before
            </p>
          )}
          {result ? (
            <>
              <ResultPanel
                result={result}
                onNext={loadNext}
                onSimilar={trySimilar}
                similarPending={similar.isPending}
                similarError={
                  similar.isError
                    ? errorMessage(similar.error, "Couldn't load a similar question.")
                    : null
                }
              />
              <TutorPanel key={`tutor-after-${item.id}`} itemId={item.id} />
            </>
          ) : (
            <>
              <QuestionCard
                key={item.id}
                item={item}
                submitting={answer.isPending}
                onSubmit={submit}
              />
              {answer.isPending && item.questionType === "extended" && (
                <p role="status" className="text-slate-700">
                  Marking your answer against the mark scheme… this can take up to a minute.
                </p>
              )}
              {answer.isError && (
                <p role="alert" className="text-red-800">
                  {errorMessage(answer.error, "Couldn't check that. Please try again.")}
                </p>
              )}
              <HintPanel
                item={item}
                pending={hint.isPending}
                onReveal={() => {
                  hint.mutate({ itemId: item.id }, { onSuccess: setServed });
                }}
              />
              <div className="flex flex-wrap gap-2">
                <LearnPanel key={`learn-${item.id}`} itemId={item.id} />
                <TutorPanel key={`tutor-${item.id}`} itemId={item.id} />
              </div>
              <FlagControl key={item.id} onSend={sendFlag} pending={flag.isPending} />
            </>
          )}
        </div>
      )}
    </AppShell>
  );
}

function HintPanel({
  item,
  pending,
  onReveal,
}: {
  item: PracticeItemOut;
  pending: boolean;
  onReveal: () => void;
}) {
  const nextIsSolution = item.hintsRemaining === 1;
  return (
    <section aria-label="Hints" className="space-y-2">
      {item.hints.length > 0 && (
        <ol className="space-y-2" aria-live="polite">
          {item.hints.map((text, index) => (
            <li key={index} className="rounded-lg bg-brand-50 p-3 text-slate-800">
              <span className="font-semibold">
                {index === 3 ? "Full solution" : `Hint ${index + 1}`}:{" "}
              </span>
              <MathText text={text} />
            </li>
          ))}
        </ol>
      )}
      {item.hintsRemaining > 0 && (
        <>
          <button
            type="button"
            onClick={onReveal}
            disabled={pending}
            className="min-h-11 rounded-lg border border-brand-700 px-4 font-semibold text-brand-700 disabled:opacity-60"
          >
            {item.hints.length === 0
              ? "I'm stuck"
              : nextIsSolution
                ? "Show full solution"
                : "Another hint"}
          </button>
          {nextIsSolution && (
            <p className="text-sm text-slate-600">
              Seeing the full solution means this one won&apos;t count towards levelling up.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function FlagControl({ onSend, pending }: { onSend: (reason: string) => void; pending: boolean }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        className="min-h-11 text-sm text-slate-600 underline"
      >
        🚩 This looks wrong
      </button>
    );
  }
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-3">
      <label className="block text-sm font-medium text-slate-800">
        What looks wrong? (optional)
        <input
          value={reason}
          maxLength={500}
          onChange={(e) => {
            setReason(e.target.value);
          }}
          className="mt-1 block min-h-11 w-full rounded-lg border border-slate-300 px-3"
        />
      </label>
      <div className="flex gap-3">
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            onSend(reason.trim());
          }}
          className="min-h-11 rounded-lg bg-slate-800 px-4 font-semibold text-white disabled:opacity-60"
        >
          Report and skip
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
          }}
          className="min-h-11 px-2 underline"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
