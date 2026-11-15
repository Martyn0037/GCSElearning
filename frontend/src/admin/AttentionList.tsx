// frontend/src/admin/AttentionList.tsx
import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  getListEnrolmentsQueryKey,
  useDeleteSetText,
  useGetCatalogue,
  useListEnrolments,
  useListSpecifications,
  useMatchSetText,
  useUpdateEnrolment,
} from "../api/generated/endpoints";
import type {
  AdminEnrolmentOut,
  AdminSpecificationOut,
  AttentionReason,
  CatalogueOut,
  EnrolmentUpdate,
  Tier,
} from "../api/generated/model";
import { ApiError } from "../api/http";
import { buttonClass } from "../components/styles";

const REASON_TEXT: Record<AttentionReason, string> = {
  no_specification: "No content loaded for this subject and board yet",
  board_unconfirmed: "Exam board not confirmed",
  tier_unconfirmed: "Tier not confirmed",
  set_text_pending: "A typed-in set text needs matching",
};

const fieldClass =
  "mt-1 block min-h-11 w-full rounded-lg border border-slate-300 bg-surface px-2 focus:outline-2 focus:outline-brand-600";

/** Students' subjects that need the admin to confirm or correct something. */
export function AttentionList() {
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const page = useListEnrolments({ attention: true, limit: 25, ...(cursor ? { cursor } : {}) });
  const catalogue = useGetCatalogue();
  const specs = useListSpecifications();

  if (page.isPending || catalogue.isPending || specs.isPending)
    return <p role="status">Loading…</p>;
  if (page.isError || catalogue.isError || specs.isError) {
    return <p role="alert">Couldn&apos;t load this list. Please refresh.</p>;
  }
  if (page.data.items.length === 0) {
    return <p className="text-slate-700">Nothing needs your attention. 🎉</p>;
  }
  return (
    <>
      <ul className="space-y-4">
        {page.data.items.map((enrolment) => (
          <li key={enrolment.id}>
            <EnrolmentCard enrolment={enrolment} catalogue={catalogue.data} specs={specs.data} />
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-3">
        {cursor && (
          <button
            type="button"
            className="min-h-11 underline"
            onClick={() => {
              setCursor(undefined);
            }}
          >
            Back to start
          </button>
        )}
        {page.data.nextCursor && (
          <button
            type="button"
            className="min-h-11 underline"
            onClick={() => {
              setCursor(page.data.nextCursor ?? undefined);
            }}
          >
            Next page
          </button>
        )}
      </div>
    </>
  );
}

interface EnrolmentCardProps {
  enrolment: AdminEnrolmentOut;
  catalogue: CatalogueOut;
  specs: readonly AdminSpecificationOut[];
}

function EnrolmentCard({ enrolment, catalogue, specs }: EnrolmentCardProps) {
  const queryClient = useQueryClient();
  const update = useUpdateEnrolment();
  const ids = { board: useId(), tier: useId(), spec: useId() };
  const subject = catalogue.subjects.find((s) => s.id === enrolment.subjectId);
  const [boardId, setBoardId] = useState(enrolment.boardId ?? "");
  const [tier, setTier] = useState<Tier | "">(enrolment.tier ?? "");
  const [specId, setSpecId] = useState(enrolment.specification?.id ?? "");
  const showTier = enrolment.isCustom || (subject?.hasTiers ?? false);
  const specChoices = specs.filter(
    (s) => enrolment.isCustom || s.subjectName === enrolment.subjectName,
  );

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: getListEnrolmentsQueryKey() });
  }

  /**
   * Send what the admin has chosen. A new spec carries its own board; otherwise
   * the board is sent (re-sending the current board just confirms it).
   */
  function confirm() {
    const newSpec = specId && specId !== enrolment.specification?.id ? specId : null;
    const data: EnrolmentUpdate = {
      ...(newSpec ? { specificationId: newSpec } : boardId ? { boardId } : {}),
      ...(tier ? { tier } : {}),
    };
    update.mutate({ enrolmentId: enrolment.id, data }, { onSuccess: refresh });
  }

  return (
    <article className="rounded-xl bg-surface p-4 shadow-sm">
      <h3 className="text-lg font-semibold">
        {enrolment.studentName}: {enrolment.subjectName}
        {enrolment.isCustom && <span className="text-sm text-slate-600"> (typed in)</span>}
      </h3>
      <ul className="mt-1 list-disc pl-5 text-sm text-amber-900">
        {enrolment.attention.map((reason) => (
          <li key={reason}>{REASON_TEXT[reason]}</li>
        ))}
      </ul>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor={ids.board} className="text-sm font-medium">
            Exam board
          </label>
          <select
            id={ids.board}
            value={boardId}
            onChange={(e) => {
              setBoardId(e.target.value);
            }}
            className={fieldClass}
          >
            <option value="">Choose…</option>
            {catalogue.boards.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>
        {showTier && (
          <div>
            <label htmlFor={ids.tier} className="text-sm font-medium">
              Tier
            </label>
            <select
              id={ids.tier}
              value={tier}
              onChange={(e) => {
                setTier(e.target.value as Tier | "");
              }}
              className={fieldClass}
            >
              <option value="">Choose…</option>
              <option value="foundation">Foundation</option>
              <option value="higher">Higher</option>
            </select>
          </div>
        )}
        <div>
          <label htmlFor={ids.spec} className="text-sm font-medium">
            Specification
          </label>
          <select
            id={ids.spec}
            value={specId}
            onChange={(e) => {
              setSpecId(e.target.value);
              const chosen = specs.find((s) => s.id === e.target.value);
              if (chosen) setBoardId(chosen.boardId);
            }}
            className={fieldClass}
          >
            <option value="">{specChoices.length ? "Choose…" : "None imported yet"}</option>
            {specChoices.map((s) => (
              <option key={s.id} value={s.id}>
                {s.boardName} {s.code} ({s.version})
              </option>
            ))}
          </select>
        </div>
      </div>
      <button
        type="button"
        onClick={confirm}
        disabled={update.isPending || (!boardId && !tier && !specId)}
        className={`mt-3 ${buttonClass("primary")}`}
      >
        Confirm
      </button>
      {update.isError && (
        <p role="alert" className="mt-2 text-red-800">
          {update.error instanceof ApiError ? update.error.message : "Couldn't save."}
        </p>
      )}

      {enrolment.setTexts.some((t) => t.status === "pending") && (
        <PendingSetTexts enrolment={enrolment} catalogue={catalogue} onChanged={refresh} />
      )}
    </article>
  );
}

function PendingSetTexts({
  enrolment,
  catalogue,
  onChanged,
}: {
  enrolment: AdminEnrolmentOut;
  catalogue: CatalogueOut;
  onChanged: () => void;
}) {
  const match = useMatchSetText();
  const remove = useDeleteSetText();
  const options =
    catalogue.subjects
      .flatMap((s) => s.specifications)
      .find((spec) => spec.id === enrolment.specification?.id)?.setTexts ?? [];

  return (
    <div className="mt-4 border-t border-slate-200 pt-3">
      <h4 className="font-medium">Typed-in set texts</h4>
      <ul className="mt-2 space-y-2">
        {enrolment.setTexts
          .filter((t) => t.status === "pending")
          .map((text) => (
            <li key={text.id} className="flex flex-wrap items-center gap-2">
              <span>
                {text.category}: <strong>{text.title}</strong>
              </span>
              <select
                aria-label={`Match ${text.title} to the board's list`}
                defaultValue=""
                disabled={options.length === 0}
                onChange={(e) => {
                  if (e.target.value) {
                    match.mutate(
                      { setTextId: text.id, data: { optionId: e.target.value } },
                      { onSuccess: onChanged },
                    );
                  }
                }}
                className="min-h-11 rounded-lg border border-slate-300 px-2"
              >
                <option value="">
                  {options.length ? "Match to…" : "Load the spec's set-text list first"}
                </option>
                {options
                  .filter((o) => o.category === text.category)
                  .map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.title}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="min-h-11 px-2 text-sm text-red-700 underline"
                onClick={() => {
                  remove.mutate({ setTextId: text.id }, { onSuccess: onChanged });
                }}
              >
                Remove
              </button>
            </li>
          ))}
      </ul>
    </div>
  );
}
