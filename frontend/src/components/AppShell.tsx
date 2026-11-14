// frontend/src/components/AppShell.tsx
import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate } from "react-router";

import type { UserOut } from "../api/generated/model";
import { useSignOut } from "../auth/useSession";

/** Page frame: top bar with the user's name and a sign-out button. */
export function AppShell({ user, children }: { user: UserOut; children: ReactNode }) {
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
    void navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-dvh bg-slate-50">
      <header className="flex items-center justify-between bg-brand-700 px-4 py-3 text-white">
        <span className="text-lg font-semibold">GCSE Coach</span>
        <div className="flex items-center gap-3">
          <span className="text-sm" aria-label="Signed in as">
            {user.displayName}
          </span>
          <button
            type="button"
            onClick={() => void handleSignOut()}
            disabled={signingOut}
            className="min-h-11 rounded-lg px-3 text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-60"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl p-4">{children}</main>
    </div>
  );
}
