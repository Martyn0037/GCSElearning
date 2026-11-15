// frontend/src/admin/StudentPasswords.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";

import {
  getListStudentsQueryKey,
  resetStudentPassword,
  useListStudents,
} from "../api/generated/endpoints";
import type { AdminStudentOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { Icon } from "../components/Icon";
import { cardClass } from "../components/styles";
import { Button, Chip, ErrorNotice, LoadingCards } from "../components/ui";
import { MAX_PASSWORD_LENGTH, passwordProblem, suggestPassword } from "./passwordSuggestion";

/**
 * Reset a student's password: pick the student, set a new password (or use a
 * suggested one), and they're signed out on every device.
 */
export function StudentPasswords() {
  const students = useListStudents();
  const [openId, setOpenId] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (students.isPending) return <LoadingCards rows={1} />;
  if (students.isError) return <ErrorNotice>Couldn&apos;t load the students.</ErrorNotice>;
  if (students.data.length === 0) {
    return <p className="text-slate-700">No student accounts yet.</p>;
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
        {students.data.map((student) => (
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
            {openId === student.id ? (
              <ResetForm
                student={student}
                onCancel={() => {
                  setOpenId(null);
                }}
                onDone={() => {
                  setOpenId(null);
                  setDone(
                    `${student.displayName}'s password has been changed and they've been signed out everywhere. Give them the new password to sign in again.`,
                  );
                }}
              />
            ) : (
              <Button
                variant="secondary"
                className="mt-3"
                onClick={() => {
                  setDone(null);
                  setOpenId(student.id);
                }}
              >
                Reset password
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
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

  const inputClass =
    "mt-1 block min-h-11 w-full rounded-xl border border-slate-300 bg-surface px-3 font-mono text-slate-900 focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

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
          className={inputClass}
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
          className={inputClass}
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
