// frontend/src/practice/ExtendedResult.tsx
import type { AnswerResultOut, ExtendedMarkingOut } from "../api/generated/model";
import { MathText } from "./MathText";

/**
 * How a written answer was marked: the mark, the level, which marking points
 * it earned (with their assessment objective), what went well and what to do
 * next, then the model answer. If Claude couldn't mark it, the mark scheme is
 * shown so the student can compare their own answer.
 */
export function ExtendedResult({ result }: { result: AnswerResultOut }) {
  const marking = result.marking as ExtendedMarkingOut;
  const unmarked = result.marked === false || marking.marks == null;
  return (
    <div className="space-y-4">
      {unmarked ? (
        <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-900">
          <span className="block text-lg font-semibold">
            We couldn&apos;t mark this one right now
          </span>
          Compare your answer with the mark scheme and model answer below. It won&apos;t count
          against you.
        </p>
      ) : (
        <p
          role="status"
          className={`rounded-xl p-4 text-xl font-semibold ${result.correct ? "bg-green-50 text-green-900" : "bg-amber-50 text-amber-900"}`}
        >
          {marking.marks} out of {marking.marksAvailable} marks
          {marking.level != null && (
            <span className="block text-base font-normal">Level {marking.level}</span>
          )}
        </p>
      )}

      {!unmarked && (marking.strengths || marking.improvements) && (
        <div className="space-y-2 rounded-lg bg-brand-50 p-3 text-slate-800">
          {marking.strengths && (
            <p>
              <span className="font-semibold">What went well: </span>
              <MathText text={marking.strengths} />
            </p>
          )}
          {marking.improvements && (
            <p>
              <span className="font-semibold">Next step: </span>
              <MathText text={marking.improvements} />
            </p>
          )}
        </div>
      )}

      <section aria-label="Mark scheme" className="rounded-lg border border-slate-200 p-3">
        <h3 className="font-semibold text-slate-900">Mark scheme</h3>
        <ul className="mt-2 space-y-1">
          {marking.points.map((point, index) => (
            <li key={index} className="flex gap-2 text-slate-800">
              <span
                aria-hidden="true"
                className={point.awarded ? "text-green-700" : "text-slate-400"}
              >
                {unmarked ? "•" : point.awarded ? "✓" : "○"}
              </span>
              <span>
                <MathText text={point.text} />{" "}
                <span className="text-sm text-slate-600">
                  ({point.ao}, {point.marks} {point.marks === 1 ? "mark" : "marks"})
                  {!unmarked && (
                    <span className="sr-only">{point.awarded ? " earned" : " not earned"}</span>
                  )}
                </span>
              </span>
            </li>
          ))}
        </ul>
        {marking.levels.length > 0 && (
          <details className="mt-2">
            <summary className="min-h-11 cursor-pointer text-sm font-medium">Levels</summary>
            <ul className="mt-1 space-y-1 text-sm text-slate-700">
              {marking.levels.map((level) => (
                <li key={level.level}>
                  <span className="font-semibold">
                    Level {level.level} ({level.minMarks}–{level.maxMarks}):
                  </span>{" "}
                  {level.descriptor}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <details className="rounded-lg bg-slate-50 p-3" open={unmarked}>
        <summary className="min-h-11 cursor-pointer font-medium">Model answer</summary>
        <p className="mt-2 whitespace-pre-line text-slate-800">
          <MathText text={result.correctAnswer} />
        </p>
      </details>
    </div>
  );
}
