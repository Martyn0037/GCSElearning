// frontend/src/pages/HomePages.tsx
// Placeholder home screens for each role. Real content arrives in later phases:
// student Home (Phase 3–5), guardian dashboard and admin tools (Phase 7).
import type { UserOut } from "../api/generated/model";
import { AppShell } from "../components/AppShell";

function Placeholder({ user, title, body }: { user: UserOut; title: string; body: string }) {
  return (
    <AppShell user={user}>
      <h1 className="mb-2 text-2xl font-bold text-slate-900">{title}</h1>
      <p className="text-slate-700">{body}</p>
    </AppShell>
  );
}

export function StudentHomePage({ user }: { user: UserOut }) {
  return (
    <Placeholder
      user={user}
      title={`Hi ${user.displayName}!`}
      body="Your questions will appear here soon."
    />
  );
}

export function GuardianHomePage({ user }: { user: UserOut }) {
  return (
    <Placeholder
      user={user}
      title="Progress dashboard"
      body="Weekly progress summaries will appear here."
    />
  );
}

export function AdminHomePage({ user }: { user: UserOut }) {
  return (
    <Placeholder
      user={user}
      title="Admin"
      body="Curriculum, review queue and costs will appear here."
    />
  );
}
