// frontend/src/pages/HomePages.tsx
// Placeholder guardian home; the real dashboard arrives in Phase 7.
import type { UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";

export function GuardianHomePage({ user }: { user: UserOut }) {
  return (
    <AppShell user={user}>
      <h1 className="mb-2 text-2xl font-bold text-slate-900">Progress dashboard</h1>
      <p className="text-slate-700">Weekly progress summaries will appear here.</p>
    </AppShell>
  );
}
