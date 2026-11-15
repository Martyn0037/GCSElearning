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
import { Icon } from "../components/Icon";
import { Button, Chip, ErrorNotice, Skeleton } from "../components/ui";
import { cardClass } from "../components/styles";
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
  // This sitting's tally, shown in the header ("3 of 4 right").
  const [tally, setTally] = useState({ answered: 0, right: 0 });

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
    answer.mutate(
      { itemId: item.id, answer: value, key },
      {
        onSuccess: (marked) => {
          if (marked.marked === false) return; // still being marked
          setTally((t) => ({
            answered: t.answered + 1,
            right: t.right + (marked.correct && !marked.assisted ? 1 : 0),
          }));
        },
      },
    );
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
      <h1 className="sr-only">Practice</h1>
      <div className="mb-4 flex min-h-11 items-center justify-between gap-3">
        <Link
          to={back.to}
          className="-ml-2 inline-flex min-h-11 items-center gap-1 rounded-lg px-2 text-sm font-medium text-brand-ink hover:bg-brand-50"
        >
          <Icon name="chevronLeft" className="size-4" />
          {back.label}
        </Link>
        {tally.answered > 0 && (
          <span
            className="inline-flex animate-fade-up items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-sm font-semibold text-slate-700 shadow-card tabular-nums"
            aria-label={`This session: ${String(tally.right)} of ${String(tally.answered)} right`}
          >
            <Icon name="check" className="size-4 text-green-800" />
            {tally.right}/{tally.answered}
          </span>
        )}
      </div>

      {next.isPending && (
        <div className={`${cardClass} space-y-4 p-5`} aria-busy="true">
          <p role="status" className="sr-only">
            Getting your next question…
          </p>
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-4/5" />
          <div className="space-y-2 pt-2">
            <Skeleton className="h-14 w-full rounded-xl" />
            <Skeleton className="h-14 w-full rounded-xl" />
          </div>
        </div>
      )}
      {finished && <div>{done.content}</div>}
      {next.isError && !finished && (
        <ErrorNotice onRetry={loadNext}>
          {errorMessage(next.error, "Couldn't load a question. Please try again.")}
        </ErrorNotice>
      )}

      {item && next.isSuccess && result && (
        <div key={`result-${item.id}`} className="animate-fade-up space-y-4">
          <div className={`${cardClass} p-5`}>
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
          </div>
          <TutorPanel key={`tutor-after-${item.id}`} itemId={item.id} />
        </div>
      )}

      {item && next.isSuccess && !result && (
        <div key={`question-${item.id}`} className="animate-fade-up space-y-4">
          <div className={`${cardClass} space-y-4 p-5`}>
            {item.review && (
              <Chip tone="warn">
                <Icon name="refresh" className="size-3.5" />
                Review: you got this one wrong before
              </Chip>
            )}
            <QuestionCard item={item} submitting={answer.isPending} onSubmit={submit} />
            {answer.isPending && item.questionType === "extended" && (
              <p role="status" className="flex items-center gap-2 text-sm text-slate-700">
                <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
                Marking your answer against the mark scheme… this can take up to a minute.
              </p>
            )}
            {answer.isError && (
              <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-900">
                {errorMessage(answer.error, "Couldn't check that. Please try again.")}
              </p>
            )}
          </div>
          <HintPanel
            item={item}
            pending={hint.isPending}
            onReveal={() => {
              hint.mutate({ itemId: item.id }, { onSuccess: setServed });
            }}
          />
          <div className="grid gap-2">
            <LearnPanel key={`learn-${item.id}`} itemId={item.id} />
            <TutorPanel key={`tutor-${item.id}`} itemId={item.id} />
          </div>
          <FlagControl key={`flag-${item.id}`} onSend={sendFlag} pending={flag.isPending} />
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
            <li
              key={index}
              className="flex animate-fade-up gap-3 rounded-2xl bg-amber-50 p-4 text-slate-800"
            >
              <Icon name="bulb" className="mt-0.5 size-5 text-amber-900" />
              <span>
                <span className="font-semibold text-amber-900">
                  {index === 3 ? "Full solution" : `Hint ${String(index + 1)}`}:{" "}
                </span>
                <MathText text={text} />
              </span>
            </li>
          ))}
        </ol>
      )}
      {item.hintsRemaining > 0 && (
        <>
          <Button variant="secondary" block icon="bulb" onClick={onReveal} disabled={pending}>
            {item.hints.length === 0
              ? "I'm stuck"
              : nextIsSolution
                ? "Show full solution"
                : "Another hint"}
          </Button>
          {nextIsSolution && (
            <p className="text-center text-sm text-slate-600">
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
        className="mx-auto flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-700"
      >
        <span aria-hidden="true">🚩</span> This looks wrong
      </button>
    );
  }
  return (
    <div className={`${cardClass} animate-fade-up space-y-3 p-4`}>
      <label className="block text-sm font-medium text-slate-800">
        What looks wrong? (optional)
        <input
          value={reason}
          maxLength={500}
          onChange={(e) => {
            setReason(e.target.value);
          }}
          className="mt-1 block min-h-11 w-full rounded-xl border border-slate-300 bg-surface px-3 focus:border-brand-600 focus:outline-2 focus:outline-brand-600"
        />
      </label>
      <div className="flex gap-3">
        <Button
          variant="neutral"
          disabled={pending}
          onClick={() => {
            onSend(reason.trim());
          }}
        >
          Report and skip
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setOpen(false);
          }}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
