// frontend/src/pages/LoginPage.tsx
import { useQueryClient } from "@tanstack/react-query";
import type { SyntheticEvent } from "react";
import { useId, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { getGetCurrentUserQueryKey, useLogin } from "../api/generated/endpoints";
import { ApiError } from "../api/http";
import { homePathForRole } from "../auth/roles";
import { useSession } from "../auth/useSession";
import { Logo } from "../components/AppShell";
import { Button } from "../components/ui";
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
    "mt-1.5 block min-h-12 w-full rounded-xl border border-slate-300 bg-surface px-4 text-lg text-slate-900 shadow-card transition focus:border-brand-600 focus:outline-2 focus:outline-brand-600";

  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-slate-50 px-4 py-10">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-brand-100 to-transparent"
      />
      <div className="relative mb-6 flex animate-fade-up flex-col items-center text-center">
        <Logo className="size-14" />
        <p className="mt-3 text-sm font-medium text-slate-600">
          Revise smarter, one question at a time.
        </p>
      </div>
      <form
        onSubmit={handleSubmit}
        noValidate
        className="relative w-full max-w-sm animate-fade-up space-y-5 rounded-3xl bg-surface p-6 shadow-raised"
        aria-describedby={hasError ? ids.error : undefined}
      >
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sign in to GCSE Coach</h1>

        {hasError && (
          <p id={ids.error} role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-900">
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

        <Button
          type="submit"
          size="lg"
          block
          disabled={login.isPending || !identifier.trim() || !password}
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>

        <p className="text-center text-sm text-slate-600">
          Forgotten your password? Ask your parent or carer to reset it.
        </p>
      </form>
      <Link
        to="/privacy"
        className="relative mt-6 inline-flex min-h-11 items-center text-sm font-medium text-slate-600 hover:text-brand-ink"
      >
        Privacy notice
      </Link>
    </main>
  );
}
