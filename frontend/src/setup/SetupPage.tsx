// frontend/src/setup/SetupPage.tsx
import { useQueryClient } from "@tanstack/react-query";
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";
import { useNavigate } from "react-router";

import {
  getGetCurrentUserQueryKey,
  getGetMySubjectsQueryKey,
  useGetCatalogue,
  useGetMySubjects,
  useReplaceMySubjects,
} from "../api/generated/endpoints";
import type { CatalogueOut, UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import type { SubjectDraft } from "./setupModel";
import {
  customKey,
  draftsFromEnrolments,
  MAX_CUSTOM_NAME,
  newCustomDraft,
  newSubjectDraft,
  toChoices,
} from "./setupModel";
import { SubjectDetails } from "./SubjectDetails";

/** First-login (and "change my subjects") screen. */
export function SetupPage({ user }: { user: UserOut }) {
  const catalogue = useGetCatalogue();
  const mine = useGetMySubjects();

  let body;
  if (catalogue.isPending || mine.isPending) {
    body = <p role="status">Loading…</p>;
  } else if (catalogue.isError || mine.isError) {
    body = <p role="alert">Couldn&apos;t load the subject list. Please refresh the page.</p>;
  } else {
    body = (
      <SetupForm
        catalogue={catalogue.data}
        initial={draftsFromEnrolments(mine.data.subjects)}
        firstTime={!user.setupCompleted}
      />
    );
  }
  return <AppShell user={user}>{body}</AppShell>;
}

interface SetupFormProps {
  catalogue: CatalogueOut;
  initial: SubjectDraft[];
  firstTime: boolean;
}

function SetupForm({ catalogue, initial, firstTime }: SetupFormProps) {
  const [drafts, setDrafts] = useState<SubjectDraft[]>(initial);
  const [customName, setCustomName] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const save = useReplaceMySubjects();
  const ids = { custom: useId(), error: useId() };
  const byKey = new Map(drafts.map((d) => [d.key, d]));
  const customDrafts = drafts.filter((d) => d.subjectId === null);

  function update(draft: SubjectDraft) {
    setDrafts((current) => current.map((d) => (d.key === draft.key ? draft : d)));
  }

  function toggle(subject: CatalogueOut["subjects"][number], checked: boolean) {
    setDrafts((current) =>
      checked
        ? [...current, newSubjectDraft(subject)]
        : current.filter((d) => d.key !== subject.id),
    );
  }

  function addCustom() {
    const name = customName.trim();
    if (!name || byKey.has(customKey(name))) return;
    setDrafts((current) => [...current, newCustomDraft(name)]);
    setCustomName("");
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { data: { subjects: toChoices(drafts, catalogue) } },
      {
        onSuccess: (result) => {
          queryClient.setQueryData(getGetMySubjectsQueryKey(), result);
          // Update the cached user before navigating, or the home page would
          // still see "not set up" and send the student straight back here.
          queryClient.setQueryData<UserOut>(getGetCurrentUserQueryKey(), (current) =>
            current ? { ...current, setupCompleted: true } : current,
          );
          void navigate("/", { replace: true });
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          {firstTime ? "Which subjects are you studying?" : "Your subjects"}
        </h1>
        <p className="mt-1 text-slate-700">
          Tick each one. If you&apos;re not sure about a board or tier, choose &quot;I don&apos;t
          know&quot;. It can be changed later.
        </p>
      </div>

      <fieldset className="space-y-2">
        <legend className="sr-only">Subjects</legend>
        {catalogue.subjects.map((subject) => {
          const draft = byKey.get(subject.id);
          return (
            <div key={subject.id} className="rounded-xl bg-white p-3 shadow-sm">
              <label className="flex min-h-11 cursor-pointer items-center gap-3 text-lg font-medium text-slate-900">
                <input
                  type="checkbox"
                  checked={draft !== undefined}
                  onChange={(e) => {
                    toggle(subject, e.target.checked);
                  }}
                  className="size-6 accent-brand-700"
                />
                {subject.name}
              </label>
              {draft && (
                <SubjectDetails
                  draft={draft}
                  subject={subject}
                  boards={catalogue.boards}
                  onChange={update}
                />
              )}
            </div>
          );
        })}
      </fieldset>

      <div className="rounded-xl bg-white p-3 shadow-sm">
        <label htmlFor={ids.custom} className="block font-medium text-slate-900">
          Studying something that isn&apos;t listed?
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id={ids.custom}
            value={customName}
            maxLength={MAX_CUSTOM_NAME}
            placeholder="e.g. Statistics"
            onChange={(e) => {
              setCustomName(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            className="block min-h-12 w-full rounded-lg border border-slate-300 px-3 text-base focus:border-brand-600 focus:outline-2 focus:outline-brand-600"
          />
          <button
            type="button"
            onClick={addCustom}
            disabled={!customName.trim()}
            className="min-h-12 rounded-lg border border-brand-700 px-4 font-semibold text-brand-700 disabled:opacity-50"
          >
            Add
          </button>
        </div>
        {customDrafts.length > 0 && (
          <ul className="mt-3 space-y-2">
            {customDrafts.map((draft) => (
              <li
                key={draft.key}
                className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2"
              >
                <span>
                  {draft.customName}{" "}
                  <span className="text-sm text-slate-600">(we&apos;ll set this one up)</span>
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setDrafts((current) => current.filter((d) => d.key !== draft.key));
                  }}
                  className="min-h-11 px-2 text-sm text-red-700 underline"
                  aria-label={`Remove ${draft.customName ?? ""}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {save.isError && (
        <p id={ids.error} role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {save.error instanceof ApiError ? save.error.message : "Couldn't save. Please try again."}
        </p>
      )}

      <button
        type="submit"
        disabled={drafts.length === 0 || save.isPending}
        className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 disabled:opacity-60"
      >
        {save.isPending ? "Saving…" : "Save my subjects"}
      </button>
    </form>
  );
}
