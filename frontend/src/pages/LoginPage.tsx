// frontend/src/pages/LoginPage.tsx
import { useQueryClient } from "@tanstack/react-query";
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { getGetCurrentUserQueryKey, useLogin } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { homePathForRole } from "../auth/roles";
import { useSession } from "../auth/useSession";
import { FullPageMessage } from "../components/FullPageMessage";

/** Where to go after login: back to the page that sent us here, if any. */
function redirectTarget(state: unknown, fallback: string): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = state.from;
    // Only same-app paths; never an absolute URL (open-redirect guard).
    if (typeof from === "string" && from.startsWith("/") && !from.startsWith("//")) {
      return from;
    }
  }
  return fallback;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

export function LoginPage() {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const login = useLogin();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const ids = { identifier: useId(), password: useId(), error: useId() };

  if (session.status === "loading") return <FullPageMessage busy>Loading…</FullPageMessage>;
  if (session.status === "signedIn") {
    return <Navigate to={homePathForRole(session.user.role)} replace />;
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    login.mutate(
      { data: { identifier, password } },
      {
        onSuccess: (result) => {
          setPassword("");
          queryClient.setQueryData(getGetCurrentUserQueryKey(), result.user);
          void navigate(redirectTarget(location.state, homePathForRole(result.user.role)), {
            replace: true,
          });
        },
      },
    );
  }

  const hasError = login.isError;
  const inputClass =
    "mt-1 block min-h-12 w-full rounded-lg border border-slate-300 px-3 text-lg focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 p-4">
      <form
        onSubmit={handleSubmit}
        noValidate
        className="w-full max-w-sm space-y-5 rounded-2xl bg-white p-6 shadow-sm"
        aria-describedby={hasError ? ids.error : undefined}
      >
        <h1 className="text-2xl font-bold text-slate-900">Sign in to GCSE Coach</h1>

        {hasError && (
          <p id={ids.error} role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
            {errorMessage(login.error)}
          </p>
        )}

        <div>
          <label htmlFor={ids.identifier} className="block font-medium text-slate-800">
            Username or email
          </label>
          <input
            id={ids.identifier}
            name="identifier"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={254}
            value={identifier}
            onChange={(e) => {
              setIdentifier(e.target.value);
            }}
            className={inputClass}
          />
        </div>

        <div>
          <label htmlFor={ids.password} className="block font-medium text-slate-800">
            Password
          </label>
          <input
            id={ids.password}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            className={inputClass}
          />
        </div>

        <button
          type="submit"
          disabled={login.isPending || !identifier.trim() || !password}
          className="min-h-12 w-full rounded-lg bg-brand-700 text-lg font-semibold text-white hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 disabled:opacity-60"
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-sm text-slate-600">
          Forgotten your password? Ask your parent or carer to reset it.
        </p>
      </form>
    </main>
  );
}
