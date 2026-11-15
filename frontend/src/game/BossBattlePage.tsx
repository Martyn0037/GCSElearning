// frontend/src/game/BossBattlePage.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import {
  answerPracticeItem,
  finishChallenge,
  getChallenge,
  nextChallengeItem,
  startBossBattle,
} from "../api/generated/endpoints";
import type { ChallengeOut, UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { MathText } from "../practice/MathText";
import { QuestionCard } from "../practice/QuestionCard";
import { describeEstimate } from "./estimate";

const START_ERRORS: Record<string, string> = {
  BOSS_LOCKED: "Practise more skills in this topic to unlock its boss battle.",
  QUESTIONS_PREPARING: "We're preparing this boss battle. Try again in a few minutes.",
  TOPIC_LOCKED: "This topic hasn't been marked as covered at school yet.",
};

/**
 * A topic's boss battle: a timed mini mock paper. No hints and no marks until
 * the end, like an exam; then the score, an estimated grade band (clearly
 * labelled), the personal best and every question with its solution.
 */
export function BossBattlePage({ user }: { user: UserOut }) {
  const { enrolmentId = "", topicId = "" } = useParams();
  const start = useMutation({ mutationFn: () => startBossBattle(enrolmentId, topicId) });
  const back = { to: `/subjects/${enrolmentId}`, label: "Back to topics" };

  return (
    <AppShell user={user}>
      <Link to={back.to} className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ {back.label}
      </Link>
      {start.isSuccess ? (
        <Battle initial={start.data} />
      ) : (
        <section className="mt-4 space-y-3 rounded-2xl bg-white p-4 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">Boss battle</h1>
          <ul className="list-disc space-y-1 pl-5 text-slate-800">
            <li>A short mock paper covering the whole topic.</li>
            <li>Timed: about a minute and a half per mark.</li>
            <li>No hints, and no marks until the end, just like the exam.</li>
          </ul>
          {start.isError && (
            <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">
              {start.error instanceof ApiError
                ? (START_ERRORS[start.error.code] ?? start.error.message)
                : "Couldn't start. Please try again."}
            </p>
          )}
          <button
            type="button"
            disabled={start.isPending}
            onClick={() => {
              start.mutate();
            }}
            className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800 disabled:opacity-60"
          >
            {start.isPending ? "Starting…" : "Start the clock"}
          </button>
        </section>
      )}
    </AppShell>
  );
}

/** Seconds left, counting down locally from the server's figure. */
function useCountdown(seconds: number | null): number | null {
  const [left, setLeft] = useState(seconds);
  const startedAt = useRef(0);
  useEffect(() => {
    if (seconds === null) return;
    startedAt.current = Date.now();
    const timer = window.setInterval(() => {
      setLeft(Math.max(0, seconds - Math.floor((Date.now() - startedAt.current) / 1000)));
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [seconds]);
  return left;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m)}:${String(s).padStart(2, "0")}`;
}

function Battle({ initial }: { initial: ChallengeOut }) {
  const queryClient = useQueryClient();
  const challengeId = initial.id;
  const state = useQuery({
    queryKey: ["challenge", challengeId],
    queryFn: () => getChallenge(challengeId),
    initialData: initial,
  });
  const finished = state.data.status === "completed";
  const next = useQuery({
    queryKey: ["challenge", challengeId, "next", state.data.answered],
    queryFn: () => nextChallengeItem(challengeId),
    enabled: !finished,
    retry: false,
  });
  const keys = useRef(new Map<string, string>());
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["challenge", challengeId] });
  const answer = useMutation({
    mutationFn: (vars: { itemId: string; answer: string }) => {
      const key = keys.current.get(vars.itemId) ?? crypto.randomUUID();
      keys.current.set(vars.itemId, key);
      return answerPracticeItem(
        vars.itemId,
        { answer: vars.answer },
        { headers: { "Idempotency-Key": key } },
      );
    },
    onSettled: () => void refresh(),
  });
  const end = useMutation({
    mutationFn: () => finishChallenge(challengeId),
    onSuccess: (data) => {
      queryClient.setQueryData(["challenge", challengeId], data);
    },
  });
  const left = useCountdown(finished ? null : (initial.secondsLeft ?? null));

  // Time's up on screen: ask the server to score it.
  const { mutate: endNow } = end;
  useEffect(() => {
    if (left === 0 && !finished) endNow();
  }, [left, finished, endNow]);
  // The server says it's over (time up or every question answered).
  const nextError = next.error;
  useEffect(() => {
    if (nextError instanceof ApiError) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextError]);

  if (finished) return <BossResults challenge={state.data} />;

  return (
    <div className="mt-4 space-y-4 rounded-2xl bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="font-semibold text-slate-900">
          {state.data.topicTitle}: question {Math.min(state.data.answered + 1, state.data.total)} of{" "}
          {state.data.total}
        </p>
        {left !== null && (
          <p
            className={`rounded-full px-3 py-1 font-mono text-lg ${left < 60 ? "bg-red-50 text-red-900" : "bg-slate-100 text-slate-900"}`}
            aria-label={`Time left ${formatTime(left)}`}
          >
            {formatTime(left)}
          </p>
        )}
      </div>
      {next.isPending && <p role="status">Loading the next question…</p>}
      {next.isSuccess && (
        <QuestionCard
          key={next.data.id}
          item={next.data}
          submitting={answer.isPending}
          onSubmit={(value) => {
            answer.mutate({ itemId: next.data.id, answer: value });
          }}
        />
      )}
      <button
        type="button"
        disabled={end.isPending}
        onClick={() => {
          end.mutate();
        }}
        className="min-h-11 text-slate-700 underline"
      >
        End the battle now
      </button>
    </div>
  );
}

function BossResults({ challenge }: { challenge: ChallengeOut }) {
  return (
    <div className="mt-4 space-y-4">
      <section className="space-y-2 rounded-2xl bg-white p-4 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Boss battle: {challenge.topicTitle}</h1>
        <p className="text-3xl font-bold text-brand-800">
          {challenge.score} / {challenge.maxScore} marks ({challenge.percent ?? 0}%)
        </p>
        {challenge.grade && (
          <p className="text-slate-800">
            <span className="font-semibold">Estimate:</span> {describeEstimate(challenge.grade)}
            <span className="block text-sm text-slate-600">
              This is a rough guide from one short test, not a predicted grade.
            </span>
          </p>
        )}
        {challenge.personalBest && challenge.previousBest != null && (
          <p className="font-semibold text-green-800">
            New personal best! (was {challenge.previousBest}%)
          </p>
        )}
        {!challenge.personalBest && challenge.previousBest != null && (
          <p className="text-slate-700">Your best on this topic: {challenge.previousBest}%</p>
        )}
        {challenge.bonusXp ? (
          <p className="font-semibold text-brand-800">+{challenge.bonusXp} bonus XP</p>
        ) : null}
      </section>
      <ol className="space-y-3">
        {challenge.results.map((r) => (
          <li key={r.position} className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
            <p className="text-sm text-slate-600">
              Question {r.position} · {r.marksEarned}/{r.marks} {r.marks === 1 ? "mark" : "marks"}
              {!r.answered && " · not answered"}
            </p>
            <p className="text-slate-900">
              <MathText text={r.stem} />
            </p>
            {r.answered && (
              <p className={r.correct ? "text-green-800" : "text-red-800"}>
                {r.correct ? "✓" : "✗"} Your answer: <MathText text={r.yourAnswer ?? ""} />
              </p>
            )}
            {!r.correct && (
              <p className="text-slate-800">
                Correct answer: <MathText text={r.correctAnswer} />
              </p>
            )}
            <details className="rounded-lg bg-slate-50 p-3">
              <summary className="min-h-11 cursor-pointer font-medium">Worked solution</summary>
              <p className="mt-2">
                <MathText text={r.workedSolution} />
              </p>
            </details>
          </li>
        ))}
      </ol>
      <Link
        to={`/subjects/${challenge.enrolmentId ?? ""}`}
        className="flex min-h-12 items-center justify-center rounded-lg bg-brand-700 font-semibold text-white"
      >
        Back to topics
      </Link>
    </div>
  );
}
