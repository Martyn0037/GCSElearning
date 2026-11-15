// frontend/src/admin/StudentAccounts.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";

import {
  getListStudentsQueryKey,
  resetStudentPassword,
  updateStudent,
  useListStudents,
} from "../api/generated/endpoints";
import type { AdminStudentOut, StudentUpdate } from "../api/generated/model";
import { ApiError } from "../api/http";
import { Icon } from "../components/Icon";
import { cardClass } from "../components/styles";
import { Button, Chip, ErrorNotice, LoadingCards } from "../components/ui";
import { MAX_PASSWORD_LENGTH, passwordProblem, suggestPassword } from "./passwordSuggestion";
import { detailsProblem, MAX_DISPLAY_NAME_LENGTH, MAX_USERNAME_LENGTH } from "./studentDetails";

type OpenForm = { id: string; form: "details" | "password" } | null;

/**
 * The students' accounts: change a student's name or username, or reset
 * their password (which signs them out on every device).
 */
export function StudentAccounts() {
  const students = useListStudents();
  const [open, setOpen] = useState<OpenForm>(null);
  const [done, setDone] = useState<string | null>(null);

  if (students.isPending) return <LoadingCards rows={1} />;
  if (students.isError) return <ErrorNotice>Couldn&apos;t load the students.</ErrorNotice>;
  if (students.data.length === 0) {
    return <p className="text-slate-700">No student accounts yet.</p>;
  }

  function openForm(id: string, form: "details" | "password") {
    setDone(null);
    setOpen({ id, form });
  }

  return (
    <div className="space-y-3">
      {done && (
        <p
          role="status"
          className="flex items-start gap-2 rounded-2xl bg-green-50 p-4 text-sm text-green-900"
        >
          <Icon name="check" className="mt-0.5 size-4" />
          {done}
        </p>
      )}
      <ul className="space-y-3">
        {students.data.map((student) => {
          const form = open?.id === student.id ? open.form : null;
          return (
            <li key={student.id} className={`${cardClass} p-4`}>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-slate-900">{student.displayName}</p>
                  <p className="text-sm text-slate-600">
                    Signs in as <span className="font-mono">{student.username ?? "—"}</span>
                  </p>
                </div>
                {student.lockedUntil && <Chip tone="warn">Locked after wrong passwords</Chip>}
              </div>
              {form === "details" && (
                <DetailsForm
                  student={student}
                  onCancel={() => {
                    setOpen(null);
                  }}
                  onDone={(saved) => {
                    setOpen(null);
                    setDone(
                      saved.username !== student.username
                        ? `Saved. ${saved.displayName} now signs in as ${saved.username ?? ""}. Their progress is kept, and they stay signed in.`
                        : `Saved. The app now calls them ${saved.displayName}.`,
                    );
                  }}
                />
              )}
              {form === "password" && (
                <ResetForm
                  student={student}
                  onCancel={() => {
                    setOpen(null);
                  }}
                  onDone={() => {
                    setOpen(null);
                    setDone(
                      `${student.displayName}'s password has been changed and they've been signed out everywhere. Give them the new password to sign in again.`,
                    );
                  }}
                />
              )}
              {form === null && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      openForm(student.id, "details");
                    }}
                  >
                    Edit details
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      openForm(student.id, "password");
                    }}
                  >
                    Reset password
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const inputClass =
  "mt-1 block min-h-11 w-full rounded-xl border border-slate-300 bg-surface px-3 text-slate-900 focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

function DetailsForm({
  student,
  onCancel,
  onDone,
}: {
  student: AdminStudentOut;
  onCancel: () => void;
  onDone: (saved: AdminStudentOut) => void;
}) {
  const ids = { name: useId(), username: useId(), hint: useId(), problem: useId() };
  const [name, setName] = useState(student.displayName);
  const [username, setUsername] = useState(student.username ?? "");
  const [tried, setTried] = useState(false);
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (changes: StudentUpdate) => updateStudent(student.id, changes),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: getListStudentsQueryKey() });
      onDone(saved);
    },
  });
  const problem = detailsProblem(name, username);
  const showProblem = tried && problem;

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (problem) return;
    // Send only what changed; nothing changed means nothing to do.
    const changes: StudentUpdate = {};
    if (name.trim() !== student.displayName) changes.displayName = name.trim();
    const cleanUsername = username.trim().toLowerCase();
    if (cleanUsername !== student.username) changes.username = cleanUsername;
    if (Object.keys(changes).length === 0) {
      onCancel();
      return;
    }
    save.mutate(changes);
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label={`Edit ${student.displayName}'s details`}
      className="mt-4 space-y-3 border-t border-slate-200 pt-4"
    >
      <div>
        <label htmlFor={ids.name} className="block text-sm font-medium text-slate-800">
          Name
        </label>
        <input
          id={ids.name}
          value={name}
          maxLength={MAX_DISPLAY_NAME_LENGTH}
          autoComplete="off"
          onChange={(e) => {
            setName(e.target.value);
          }}
          className={inputClass}
        />
      </div>
      <div>
        <label htmlFor={ids.username} className="block text-sm font-medium text-slate-800">
          Username
        </label>
        <input
          id={ids.username}
          value={username}
          maxLength={MAX_USERNAME_LENGTH}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          onChange={(e) => {
            setUsername(e.target.value);
          }}
          aria-describedby={ids.hint}
          className={`${inputClass} font-mono`}
        />
        <p id={ids.hint} className="mt-1 text-sm text-slate-600">
          What they type to sign in: 3–32 lower-case letters, numbers, dots, hyphens or underscores.
        </p>
      </div>
      {showProblem && (
        <p id={ids.problem} role="alert" className="text-sm text-red-800">
          {problem}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-sm text-red-800">
          {save.error instanceof ApiError
            ? save.error.message
            : "Couldn't save the changes. Please try again."}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={save.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function ResetForm({
  student,
  onCancel,
  onDone,
}: {
  student: AdminStudentOut;
  onCancel: () => void;
  onDone: () => void;
}) {
  const ids = { password: useId(), confirm: useId(), problem: useId() };
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [tried, setTried] = useState(false);
  const queryClient = useQueryClient();
  const reset = useMutation({
    mutationFn: (newPassword: string) => resetStudentPassword(student.id, { newPassword }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: getListStudentsQueryKey() });
      onDone();
    },
  });
  const problem = passwordProblem(password, confirm);
  const showProblem = tried && problem;

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (!problem) reset.mutate(password);
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label={`Reset ${student.displayName}'s password`}
      className="mt-4 space-y-3 border-t border-slate-200 pt-4"
    >
      <div>
        <label htmlFor={ids.password} className="block text-sm font-medium text-slate-800">
          New password
        </label>
        <input
          id={ids.password}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          maxLength={MAX_PASSWORD_LENGTH}
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
          }}
          aria-invalid={Boolean(showProblem)}
          aria-describedby={showProblem ? ids.problem : undefined}
          className={`${inputClass} font-mono`}
        />
      </div>
      <div>
        <label htmlFor={ids.confirm} className="block text-sm font-medium text-slate-800">
          Type it again
        </label>
        <input
          id={ids.confirm}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          maxLength={MAX_PASSWORD_LENGTH}
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
          }}
          aria-invalid={Boolean(showProblem)}
          aria-describedby={showProblem ? ids.problem : undefined}
          className={`${inputClass} font-mono`}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="ghost"
          icon="sparkles"
          onClick={() => {
            const suggestion = suggestPassword();
            setPassword(suggestion);
            setConfirm(suggestion);
            setVisible(true);
          }}
        >
          Suggest one
        </Button>
        <Button
          variant="ghost"
          aria-pressed={visible}
          onClick={() => {
            setVisible((v) => !v);
          }}
        >
          {visible ? "Hide" : "Show"}
        </Button>
      </div>
      {showProblem && (
        <p id={ids.problem} role="alert" className="text-sm text-red-800">
          {problem}
        </p>
      )}
      {reset.isError && (
        <p role="alert" className="text-sm text-red-800">
          {reset.error instanceof ApiError
            ? reset.error.message
            : "Couldn't change the password. Please try again."}
        </p>
      )}
      <p className="text-sm text-slate-600">
        At least 10 characters. {student.displayName} will be signed out on every device.
      </p>
      <div className="flex gap-2">
        <Button type="submit" disabled={reset.isPending}>
          {reset.isPending ? "Saving…" : "Set new password"}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={reset.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
