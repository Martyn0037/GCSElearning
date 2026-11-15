// frontend/src/practice/QuestionCard.tsx
import type { SyntheticEvent } from "react";
import { useId, useRef, useState } from "react";

import type { PracticeItemOut } from "../api/generated/model";
import { Icon } from "../components/Icon";
import { Button, Chip } from "../components/ui";
import { answerAsLatex } from "./answerPreview";
import type { Edit } from "./editing";
import { deleteBack, ESSAY_MAX_LENGTH, insertAt, MAX_LENGTH } from "./editing";
import { MathKeypad } from "./MathKeypad";
import { MathText } from "./MathText";

interface QuestionCardProps {
  item: PracticeItemOut;
  submitting: boolean;
  onSubmit: (answer: string) => void;
}

const inputClass =
  "mt-1.5 block min-h-13 w-full rounded-xl border border-slate-300 bg-surface px-4 text-lg text-slate-900 shadow-card transition focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

/** One question with the right answer control for its type. */
export function QuestionCard({ item, submitting, onSubmit }: QuestionCardProps) {
  const [answer, setAnswer] = useState("");
  // Phones: for maths answers the on-screen keys replace the system keyboard
  // unless asked for; word answers keep the keyboard, with the keys below.
  const [useKeyboard, setUseKeyboard] = useState(false);
  const ids = { answer: useId(), stem: useId(), hint: useId() };
  const input = useRef<HTMLInputElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  // Written answers get a large box; everything else a single line.
  const essay = item.questionType === "extended";
  const maxLength = essay ? ESSAY_MAX_LENGTH : MAX_LENGTH;
  const keysOnly = item.keypad && !useKeyboard;
  // The maths preview only makes sense where maths can be typed.
  const preview = essay || !item.numberKeys ? null : answerAsLatex(answer);
  const words = answer.trim() ? answer.trim().split(/\s+/).length : 0;

  /** Apply a key press at the caret (or over the selection), then put the caret after it. */
  function edit(change: (value: string, start: number, end: number) => Edit) {
    const element = essay ? area.current : input.current;
    const start = element?.selectionStart ?? answer.length;
    const end = element?.selectionEnd ?? start;
    const next = change(answer, start, end);
    setAnswer(next.value);
    requestAnimationFrame(() => {
      // Keep typing where the key left off (and, on a phone, keep the keyboard
      // open for word answers). Maths answers suppress the keyboard via inputMode.
      element?.focus();
      element?.setSelectionRange(next.caret, next.caret);
    });
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (answer.trim()) onSubmit(answer.trim());
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" aria-labelledby={ids.stem}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
        <span className="flex items-center gap-2">
          <Chip tone="brand">Skill {item.objectiveRef}</Chip>
          <span
            aria-hidden="true"
            className="flex gap-0.5"
            title={`Level ${String(item.difficulty)}`}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <span
                key={n}
                className={`h-1.5 w-3 rounded-full ${n <= item.difficulty ? "bg-brand-600" : "bg-slate-200"}`}
              />
            ))}
          </span>
          <span className="sr-only">
            Skill {item.objectiveRef} · Level {item.difficulty}
          </span>
        </span>
        <Chip>
          [{item.marks} {item.marks === 1 ? "mark" : "marks"}]
        </Chip>
      </div>
      <p id={ids.stem} className="text-xl leading-relaxed font-medium text-slate-900">
        <MathText text={item.stem} />
      </p>

      {item.questionType === "multiple_choice" ? (
        <fieldset>
          <legend className="sr-only">Choose one answer</legend>
          <div className="grid gap-2">
            {item.options.map((option) => (
              <label
                key={option.label}
                className="group flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-surface px-3 py-2 text-lg text-slate-900 shadow-card transition hover:border-brand-500 active:scale-[0.99] has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50 has-[:checked]:ring-1 has-[:checked]:ring-brand-600 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600"
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
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-sm font-bold text-slate-700 transition group-has-[:checked]:bg-brand-600 group-has-[:checked]:text-white">
                  {option.label}
                </span>
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
            {essay ? (
              <textarea
                ref={area}
                id={ids.answer}
                value={answer}
                onChange={(e) => {
                  setAnswer(e.target.value);
                }}
                rows={10}
                maxLength={ESSAY_MAX_LENGTH}
                spellCheck
                aria-describedby={ids.hint}
                className={`${inputClass} py-2 leading-relaxed`}
              />
            ) : (
              <input
                ref={input}
                id={ids.answer}
                value={answer}
                onChange={(e) => {
                  setAnswer(e.target.value);
                }}
                maxLength={MAX_LENGTH}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                inputMode={keysOnly ? "none" : item.questionType === "numeric" ? "decimal" : "text"}
                aria-describedby={ids.hint}
                className={inputClass}
              />
            )}
            {item.unit && <span className="text-lg font-medium text-slate-700">{item.unit}</span>}
          </div>
          {preview && (
            <p
              className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-lg text-slate-800"
              aria-live="polite"
            >
              <span className="text-sm text-slate-600">Looks like: </span>
              <MathText text={`$${preview}$`} />
            </p>
          )}
          {essay && (
            <p className="mt-1 text-sm text-slate-600" aria-live="polite">
              {words} {words === 1 ? "word" : "words"}
            </p>
          )}
          <p id={ids.hint} className="mt-1 text-sm text-slate-600">
            {essay
              ? `Write your answer in full sentences. It's marked out of ${String(item.marks)} against the mark scheme.`
              : item.keypad
                ? "Tap the keys or type. For a fraction, use a/b: 3 a/b 5 gives 3/5."
                : item.numberKeys
                  ? "Type your answer. Numbers and symbols are on the keys below."
                  : item.symbolKeys.length > 0
                    ? "Type your answer. Accented letters are on the keys below."
                    : "Type your answer."}
            {item.symbolKeys.includes("π") && " For π, use the π key: 1 a/b 2 π gives ½π."}
          </p>
          {(item.numberKeys || item.symbolKeys.length > 0) && (
            <div className="mt-3">
              <MathKeypad
                numberKeys={item.numberKeys}
                symbols={item.symbolKeys}
                onInsert={(text) => {
                  edit((value, start, end) => insertAt(value, text, start, end, maxLength));
                }}
                onBackspace={() => {
                  edit(deleteBack);
                }}
                onClear={() => {
                  setAnswer("");
                }}
              />
            </div>
          )}
          {item.keypad && (
            <Button
              variant="ghost"
              className="mt-2"
              onClick={() => {
                setUseKeyboard((current) => !current);
              }}
            >
              {useKeyboard ? "Use the on-screen keys only" : "Use keyboard instead"}
            </Button>
          )}
        </div>
      )}

      <Button type="submit" size="lg" block disabled={!answer.trim() || submitting}>
        {submitting ? (
          <>
            <span className="size-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Checking…
          </>
        ) : (
          <>
            Check answer
            <Icon name="check" className="size-5" />
          </>
        )}
      </Button>
    </form>
  );
}
