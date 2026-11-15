// frontend/src/practice/ResultPanel.tsx
import { getMyMistake, getGetMyMistakeQueryKey } from "../api/generated/endpoints";
import type { AnswerResultOut, MistakeOut } from "../api/generated/model";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "../components/Icon";
import { Button } from "../components/ui";
import { RewardsPanel } from "../game/RewardsPanel";
import { ExtendedResult } from "./ExtendedResult";
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
  const wrong = (!result.correct || result.assisted) && result.marked !== false;
  const written = result.marking != null;
  return (
    <div className="space-y-4" aria-live="polite">
      {written ? (
        <ExtendedResult result={result} />
      ) : (
        <div
          role="status"
          className={`flex items-center gap-4 rounded-2xl p-4 ${result.correct ? "bg-green-50 text-green-900" : "bg-red-50 text-red-900"}`}
        >
          <span
            className={`grid size-12 shrink-0 animate-pop place-items-center rounded-full text-white ${result.correct ? "bg-green-600" : "bg-red-600"}`}
          >
            <Icon name={result.correct ? "check" : "x"} className="size-6" />
          </span>
          <span>
            <span className="block text-xl font-bold">
              {result.correct ? "Correct!" : "Not quite"}
            </span>
            {result.assisted && (
              <span className="block text-sm">You used the full solution for this one.</span>
            )}
          </span>
        </div>
      )}

      {result.rewards && <RewardsPanel rewards={result.rewards} challenge={result.challenge} />}

      {result.review && result.mistakeResolved && (
        <p className="rounded-xl bg-green-50 p-3 font-semibold text-green-800">
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

      {!result.correct && !written && (
        <p className="rounded-xl border border-slate-200 p-3 text-slate-800">
          <span className="block text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Correct answer
          </span>
          <span className="sr-only">Correct answer: </span>
          <span className="text-lg font-semibold">
            <MathText text={result.correctAnswer} />
          </span>
        </p>
      )}
      {result.mistakeId && wrong && <MistakeExplanation mistakeId={result.mistakeId} />}

      {levelChange > 0 && (
        <p className="flex items-center gap-2 rounded-xl bg-brand-50 p-3 font-semibold text-brand-ink">
          <Icon name="sparkles" className="size-5" />
          Level up! You&apos;re now on level {result.levelAfter}.
        </p>
      )}
      {levelChange < 0 && (
        <p className="text-slate-700">Let&apos;s rebuild on level {result.levelAfter} for a bit.</p>
      )}

      <details
        className="group rounded-xl bg-slate-50 px-4 open:pb-4"
        open={!result.correct && !written}
      >
        <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between font-semibold text-slate-800 [&::-webkit-details-marker]:hidden">
          Worked solution
          <Icon
            name="chevronDown"
            className="size-4 text-slate-500 transition-transform group-open:rotate-180"
          />
        </summary>
        <p className="leading-relaxed text-slate-800">
          <MathText text={result.workedSolution} />
        </p>
      </details>

      <div className="space-y-2 pt-1">
        <Button size="lg" block onClick={onNext}>
          {result.challenge?.completed ? "See results" : "Next question"}
          <Icon name="chevronRight" className="size-5" />
        </Button>
        {wrong && !result.review && (
          <>
            <Button
              variant="secondary"
              size="lg"
              block
              icon="refresh"
              onClick={onSimilar}
              disabled={similarPending}
            >
              {similarPending ? "Finding one…" : "Try a similar one"}
            </Button>
            {similarError && (
              <p role="alert" className="text-sm text-amber-900">
                {similarError}
              </p>
            )}
          </>
        )}
      </div>
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
      <p
        role="status"
        className="flex items-center gap-2 rounded-xl bg-brand-50 p-3 text-slate-700"
      >
        <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        Working out where it went wrong…
      </p>
    );
  }
  return (
    <section
      aria-label="Where it went wrong"
      className="animate-fade-up rounded-xl border-l-4 border-brand-600 bg-brand-50 p-4 text-slate-800"
    >
      <h3 className="font-semibold text-brand-ink">Where it went wrong</h3>
      <p className="mt-1">
        <MathText text={data.explanation ?? ""} />
      </p>
      {data.misconception && (
        <p className="mt-2 text-sm text-slate-600">Common slip: {data.misconception}</p>
      )}
    </section>
  );
}
