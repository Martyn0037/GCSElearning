// frontend/src/practice/QuestionCard.tsx
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";

import type { PracticeItemOut } from "../api/generated/model";
import { MathText } from "./MathText";

interface QuestionCardProps {
  item: PracticeItemOut;
  submitting: boolean;
  onSubmit: (answer: string) => void;
}

const inputClass =
  "mt-1 block min-h-12 w-full rounded-lg border border-slate-300 px-3 text-lg focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

/** One question with the right answer control for its type. */
export function QuestionCard({ item, submitting, onSubmit }: QuestionCardProps) {
  const [answer, setAnswer] = useState("");
  const ids = { answer: useId(), stem: useId() };

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (answer.trim()) onSubmit(answer.trim());
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" aria-labelledby={ids.stem}>
      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>
          Skill {item.objectiveRef} · Level {item.difficulty}
        </span>
        <span>
          [{item.marks} {item.marks === 1 ? "mark" : "marks"}]
        </span>
      </div>
      <p id={ids.stem} className="text-xl leading-relaxed text-slate-900">
        <MathText text={item.stem} />
      </p>

      {item.questionType === "multiple_choice" ? (
        <fieldset>
          <legend className="sr-only">Choose one answer</legend>
          <div className="grid gap-2">
            {item.options.map((option) => (
              <label
                key={option.label}
                className="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border border-slate-300 bg-white px-4 text-lg has-[:checked]:border-brand-700 has-[:checked]:bg-brand-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600"
              >
                <input
                  type="radio"
                  name="answer"
                  value={option.label}
                  checked={answer === option.label}
                  onChange={() => {
                    setAnswer(option.label);
                  }}
                  className="sr-only"
                />
                <span className="font-semibold text-brand-700">{option.label}</span>
                <MathText text={option.text} />
              </label>
            ))}
          </div>
        </fieldset>
      ) : (
        <div>
          <label htmlFor={ids.answer} className="block font-medium text-slate-800">
            Your answer
          </label>
          <div className="flex items-center gap-2">
            <input
              id={ids.answer}
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
              }}
              maxLength={200}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              inputMode={item.questionType === "numeric" ? "decimal" : "text"}
              className={inputClass}
            />
            {item.unit && <span className="text-lg text-slate-700">{item.unit}</span>}
          </div>
          {item.questionType === "numeric" && (
            <p className="mt-1 text-sm text-slate-600">You can type a fraction like 7/2.</p>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={!answer.trim() || submitting}
        className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 disabled:opacity-60"
      >
        {submitting ? "Checking…" : "Check answer"}
      </button>
    </form>
  );
}
