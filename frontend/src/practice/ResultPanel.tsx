// frontend/src/practice/ResultPanel.tsx
import { getMyMistake, getGetMyMistakeQueryKey } from "../api/generated/endpoints";
import type { AnswerResultOut, MistakeOut } from "../api/generated/model";
import { useQuery } from "@tanstack/react-query";
import { RewardsPanel } from "../game/RewardsPanel";
import { MathText } from "./MathText";

/** How often, and how many times, to check for the explanation. */
export const EXPLANATION_POLL_MS = 2000;
export const EXPLANATION_MAX_POLLS = 20;

interface ResultPanelProps {
  result: AnswerResultOut;
  onNext: () => void;
  onSimilar: () => void;
  similarPending: boolean;
  similarError: string | null;
}

/** The marked answer, with the explanation (wrong answers) and what to do next. */
export function ResultPanel({
  result,
  onNext,
  onSimilar,
  similarPending,
  similarError,
}: ResultPanelProps) {
  const levelChange = result.levelAfter - result.levelBefore;
  const wrong = !result.correct || result.assisted;
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

      {result.rewards && <RewardsPanel rewards={result.rewards} challenge={result.challenge} />}

      {result.review && result.mistakeResolved && (
        <p className="font-semibold text-green-800">
          Fixed! You won&apos;t see this mistake again.
        </p>
      )}
      {result.review && !result.mistakeResolved && (
        <p className="text-slate-700">
          {result.correct
            ? "Nice. One more right on another day and it's fixed."
            : "We'll bring this one back tomorrow."}
        </p>
      )}

      {!result.correct && (
        <p className="text-slate-800">
          Correct answer: <MathText text={result.correctAnswer} />
        </p>
      )}
      {result.mistakeId && wrong && <MistakeExplanation mistakeId={result.mistakeId} />}

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

      {wrong && !result.review && (
        <>
          <button
            type="button"
            onClick={onSimilar}
            disabled={similarPending}
            className="min-h-12 w-full rounded-lg border-2 border-brand-700 text-lg font-semibold text-brand-700 disabled:opacity-60"
          >
            {similarPending ? "Finding one…" : "Try a similar one"}
          </button>
          {similarError && (
            <p role="alert" className="text-amber-900">
              {similarError}
            </p>
          )}
        </>
      )}
      <button
        type="button"
        onClick={onNext}
        className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800"
      >
        {result.challenge?.completed ? "See results" : "Next question"}
      </button>
    </div>
  );
}

/** "Where it went wrong": polls until the worker has written it (or gives up quietly). */
function MistakeExplanation({ mistakeId }: { mistakeId: string }) {
  const query = useQuery({
    queryKey: getGetMyMistakeQueryKey(mistakeId),
    queryFn: ({ signal }) => getMyMistake(mistakeId, { signal }),
    refetchInterval: (q) => {
      const data: MistakeOut | undefined = q.state.data;
      const pending = !data || data.explanationStatus === "pending";
      return pending && q.state.dataUpdateCount < EXPLANATION_MAX_POLLS
        ? EXPLANATION_POLL_MS
        : false;
    },
  });
  const data = query.data;
  if (!data || data.explanationStatus === "unavailable") return null;
  if (data.explanationStatus === "pending") {
    return (
      <p role="status" className="rounded-lg bg-brand-50 p-3 text-slate-700">
        Working out where it went wrong…
      </p>
    );
  }
  return (
    <section aria-label="Where it went wrong" className="rounded-lg bg-brand-50 p-3 text-slate-800">
      <h3 className="font-semibold">Where it went wrong</h3>
      <p className="mt-1">
        <MathText text={data.explanation ?? ""} />
      </p>
      {data.misconception && (
        <p className="mt-2 text-sm text-slate-600">Common slip: {data.misconception}</p>
      )}
    </section>
  );
}
