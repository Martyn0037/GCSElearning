// frontend/src/practice/QuestionCard.tsx
import type { SyntheticEvent } from "react";
import { useId, useRef, useState } from "react";

import type { PracticeItemOut } from "../api/generated/model";
import { answerAsLatex } from "./answerPreview";
import type { Edit } from "./editing";
import { deleteBack, insertAt } from "./editing";
import { MathKeypad } from "./MathKeypad";
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
  // Phones: for maths answers the on-screen keys replace the system keyboard
  // unless asked for; word answers keep the keyboard, with the keys below.
  const [useKeyboard, setUseKeyboard] = useState(false);
  const ids = { answer: useId(), stem: useId(), hint: useId() };
  const input = useRef<HTMLInputElement>(null);
  const keysOnly = item.keypad && !useKeyboard;
  const preview = answerAsLatex(answer);

  /** Apply a key press at the caret (or over the selection), then put the caret after it. */
  function edit(change: (value: string, start: number, end: number) => Edit) {
    const element = input.current;
    const start = element?.selectionStart ?? answer.length;
    const end = element?.selectionEnd ?? start;
    const next = change(answer, start, end);
    setAnswer(next.value);
    requestAnimationFrame(() => {
      element?.setSelectionRange(next.caret, next.caret);
    });
  }

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
              ref={input}
              id={ids.answer}
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
              }}
              maxLength={200}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              inputMode={keysOnly ? "none" : item.questionType === "numeric" ? "decimal" : "text"}
              aria-describedby={ids.hint}
              className={inputClass}
            />
            {item.unit && <span className="text-lg text-slate-700">{item.unit}</span>}
          </div>
          {preview && (
            <p className="mt-2 text-lg text-slate-800" aria-live="polite">
              Looks like: <MathText text={`$${preview}$`} />
            </p>
          )}
          <p id={ids.hint} className="mt-1 text-sm text-slate-600">
            {item.keypad
              ? "Tap the keys or type. For a fraction, use a/b: 3 a/b 5 gives 3/5."
              : "Type your answer. Numbers and symbols are on the keys below."}
            {item.symbolKeys.includes("π") && " For π, use the π key: 1 a/b 2 π gives ½π."}
          </p>
          <div className="mt-3">
            <MathKeypad
              symbols={item.symbolKeys}
              onInsert={(text) => {
                edit((value, start, end) => insertAt(value, text, start, end));
              }}
              onBackspace={() => {
                edit(deleteBack);
              }}
              onClear={() => {
                setAnswer("");
              }}
            />
          </div>
          {item.keypad && (
            <button
              type="button"
              className="mt-2 min-h-11 text-sm font-medium text-brand-700 underline"
              onClick={() => {
                setUseKeyboard((current) => !current);
              }}
            >
              {useKeyboard ? "Use the on-screen keys only" : "Use keyboard instead"}
            </button>
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
