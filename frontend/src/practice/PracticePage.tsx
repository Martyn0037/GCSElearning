// frontend/src/practice/PracticePage.tsx
import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import {
  answerPracticeItem,
  useFlagPracticeItem,
  useNextPracticeItem,
  useRevealHint,
} from "../api/generated/endpoints";
import type { AnswerResultOut, PracticeItemOut, UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { MathText } from "./MathText";
import { QuestionCard } from "./QuestionCard";

const LOAD_ERRORS: Record<string, string> = {
  QUESTIONS_PREPARING: "We're preparing questions for this topic. Try again in a minute.",
  TOPIC_LOCKED: "This topic hasn't been marked as covered at school yet.",
  SUBJECT_NOT_READY: "This subject is still being set up.",
};

function message(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return LOAD_ERRORS[error.code] ?? error.message;
  return fallback;
}

/** One question at a time for a topic: answer, get help, see the result, carry on. */
export function PracticePage({ user }: { user: UserOut }) {
  const { enrolmentId = "", topicId = "" } = useParams();
  const next = useNextPracticeItem();
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
  const { reset: resetHint } = hint;
  const { reset: resetAnswer } = answer;
  const loadNext = useCallback(() => {
    resetHint();
    resetAnswer();
    requestNext({ enrolmentId, topicId });
  }, [requestNext, resetHint, resetAnswer, enrolmentId, topicId]);

  useEffect(() => {
    loadNext();
  }, [loadNext]);

  // The question on screen: the latest hint response if it's for this item.
  const served = next.data;
  const item = hint.data && hint.data.id === served?.id ? hint.data : served;
  const result = answer.data && answer.data.itemId === item?.id ? answer.data : null;

  function submit(value: string) {
    if (!item) return;
    const key = keys.current.get(item.id) ?? crypto.randomUUID();
    keys.current.set(item.id, key);
    answer.mutate({ itemId: item.id, answer: value, key });
  }

  function revealHint() {
    if (item) hint.mutate({ itemId: item.id });
  }

  function sendFlag(reason: string) {
    if (!item) return;
    flag.mutate({ itemId: item.id, data: reason ? { reason } : {} }, { onSuccess: loadNext });
  }

  return (
    <AppShell user={user}>
      <Link
        to={`/subjects/${enrolmentId}`}
        className="inline-flex min-h-11 items-center text-brand-700 underline"
      >
        ‹ Back to topics
      </Link>

      {next.isPending && (
        <p role="status" className="mt-6 text-slate-700">
          Getting your next question…
        </p>
      )}
      {next.isError && (
        <div role="alert" className="mt-6 space-y-3 rounded-xl bg-amber-50 p-4 text-amber-900">
          <p>{message(next.error, "Couldn't load a question. Please try again.")}</p>
          <button type="button" onClick={loadNext} className="min-h-11 font-semibold underline">
            Try again
          </button>
        </div>
      )}

      {item && next.isSuccess && (
        <div className="mt-4 space-y-4 rounded-2xl bg-white p-4 shadow-sm">
          {result ? (
            <ResultPanel result={result} onNext={loadNext} />
          ) : (
            <>
              <QuestionCard
                key={item.id}
                item={item}
                submitting={answer.isPending}
                onSubmit={submit}
              />
              {answer.isError && (
                <p role="alert" className="text-red-800">
                  {message(answer.error, "Couldn't check that. Please try again.")}
                </p>
              )}
              <HintPanel item={item} pending={hint.isPending} onReveal={revealHint} />
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

function ResultPanel({ result, onNext }: { result: AnswerResultOut; onNext: () => void }) {
  const levelChange = result.levelAfter - result.levelBefore;
  return (
    <div className="space-y-4" aria-live="polite">
      <p
        role="status"
        className={`rounded-xl p-4 text-xl font-semibold ${result.correct ? "bg-green-50 text-green-900" : "bg-red-50 text-red-900"}`}
      >
        {result.correct ? "✓ Correct!" : "✗ Not quite"}
        {result.assisted && (
          <span className="block text-base font-normal">
            You used the full solution for this one.
          </span>
        )}
      </p>
      {!result.correct && (
        <p className="text-slate-800">
          Correct answer: <MathText text={result.correctAnswer} />
        </p>
      )}
      {levelChange > 0 && (
        <p className="font-semibold text-brand-700">
          Level up! You&apos;re now on level {result.levelAfter}.
        </p>
      )}
      {levelChange < 0 && (
        <p className="text-slate-700">Let&apos;s rebuild on level {result.levelAfter} for a bit.</p>
      )}
      <details className="rounded-lg bg-slate-50 p-3" open={!result.correct}>
        <summary className="min-h-11 cursor-pointer font-medium">Worked solution</summary>
        <p className="mt-2 text-slate-800">
          <MathText text={result.workedSolution} />
        </p>
      </details>
      <button
        type="button"
        onClick={onNext}
        className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800"
      >
        Next question
      </button>
    </div>
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
