// frontend/src/setup/SubjectDetails.tsx
import { useId } from "react";

import type { BoardOut, CatalogueSubjectOut } from "../api/generated/model";
import type { SetTextDraft, SubjectDraft } from "./setupModel";
import { specFor } from "./setupModel";

const OTHER = "__other__";
const SKIP = "__skip__";

interface SubjectDetailsProps {
  draft: SubjectDraft;
  subject: CatalogueSubjectOut;
  boards: readonly BoardOut[];
  onChange: (draft: SubjectDraft) => void;
}

const fieldClass =
  "mt-1 block min-h-12 w-full rounded-lg border border-slate-300 bg-surface px-3 text-base focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

/** Board, tier and set-text choices for one chosen catalogue subject. */
export function SubjectDetails({ draft, subject, boards, onChange }: SubjectDetailsProps) {
  const ids = { board: useId(), boardHint: useId(), tierHint: useId() };
  const spec = specFor(draft, subject);
  const mostCommon = boards.find((b) => b.id === subject.mostCommonBoardId);

  return (
    <div className="mt-3 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div>
        <label htmlFor={ids.board} className="block font-medium text-slate-800">
          Exam board
        </label>
        <select
          id={ids.board}
          value={draft.board}
          aria-describedby={ids.boardHint}
          onChange={(e) => {
            // Options from one board's list don't apply to another; typed titles do.
            const typed = Object.fromEntries(
              Object.entries(draft.setTexts).filter(([, t]) => t.kind === "custom"),
            );
            onChange({ ...draft, board: e.target.value, setTexts: typed });
          }}
          className={fieldClass}
        >
          <option value="unknown">I don&apos;t know</option>
          {boards.map((board) => (
            <option key={board.id} value={board.id}>
              {board.name}
              {board.id === subject.mostCommonBoardId ? " (most schools)" : ""}
            </option>
          ))}
        </select>
        <p id={ids.boardHint} className="mt-1 text-sm text-slate-600">
          {draft.board === "unknown" && mostCommon
            ? `We'll start with ${mostCommon.name}, the board most schools use. It can be changed later.`
            : "Your teacher or exercise book will say which board you're on."}
        </p>
      </div>

      {subject.hasTiers && (
        <fieldset aria-describedby={ids.tierHint}>
          <legend className="font-medium text-slate-800">Tier</legend>
          <div className="mt-1 grid grid-cols-3 gap-2">
            {(
              [
                ["foundation", "Foundation"],
                ["higher", "Higher"],
                ["unknown", "Not sure"],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                className="flex min-h-12 cursor-pointer items-center justify-center rounded-lg border border-slate-300 bg-surface px-2 text-center has-[:checked]:border-brand-700 has-[:checked]:bg-brand-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600"
              >
                <input
                  type="radio"
                  name={`tier-${draft.key}`}
                  value={value}
                  checked={draft.tier === value}
                  onChange={() => {
                    onChange({ ...draft, tier: value });
                  }}
                  className="sr-only"
                />
                {label}
              </label>
            ))}
          </div>
          <p id={ids.tierHint} className="mt-1 text-sm text-slate-600">
            Not sure? We&apos;ll use Higher. Questions still start easy.
          </p>
        </fieldset>
      )}

      {subject.setTextCategories.map((category) => (
        <SetTextField
          key={category}
          category={category}
          options={spec?.setTexts.filter((t) => t.category === category) ?? []}
          value={draft.setTexts[category] ?? { kind: "none" }}
          onChange={(value) => {
            onChange({ ...draft, setTexts: { ...draft.setTexts, [category]: value } });
          }}
        />
      ))}

      {!spec && (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          We&apos;re still adding this board&apos;s content. This subject will appear once it&apos;s
          ready.
        </p>
      )}
    </div>
  );
}

interface SetTextFieldProps {
  category: string;
  options: readonly { id: string; title: string; author: string | null }[];
  value: SetTextDraft;
  onChange: (value: SetTextDraft) => void;
}

/** Pick a set text from the board's list, or type one in. */
function SetTextField({ category, options, value, onChange }: SetTextFieldProps) {
  const ids = { select: useId(), input: useId() };
  const selected =
    value.kind === "option" ? value.optionId : value.kind === "custom" ? OTHER : SKIP;
  const showInput = value.kind === "custom" || options.length === 0;

  return (
    <div>
      {options.length > 0 && (
        <>
          <label htmlFor={ids.select} className="block font-medium text-slate-800">
            {category}
          </label>
          <select
            id={ids.select}
            value={selected}
            onChange={(e) => {
              const next = e.target.value;
              onChange(
                next === SKIP
                  ? { kind: "none" }
                  : next === OTHER
                    ? { kind: "custom", title: "" }
                    : { kind: "option", optionId: next },
              );
            }}
            className={fieldClass}
          >
            <option value={SKIP}>Choose later</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.title}
                {option.author ? ` — ${option.author}` : ""}
              </option>
            ))}
            <option value={OTHER}>Something else (type it)</option>
          </select>
        </>
      )}
      {showInput && (
        <>
          <label
            htmlFor={ids.input}
            className={options.length > 0 ? "sr-only" : "block font-medium text-slate-800"}
          >
            {options.length > 0 ? `${category}: type the title` : `${category} (optional)`}
          </label>
          <input
            id={ids.input}
            value={value.kind === "custom" ? value.title : ""}
            maxLength={200}
            placeholder="Type the title"
            onChange={(e) => {
              onChange(
                e.target.value ? { kind: "custom", title: e.target.value } : { kind: "none" },
              );
            }}
            className={fieldClass}
          />
        </>
      )}
    </div>
  );
}
