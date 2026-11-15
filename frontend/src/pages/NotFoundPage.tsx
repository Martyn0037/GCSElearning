// frontend/src/pages/NotFoundPage.tsx
import { Logo } from "../components/AppShell";
import { ButtonLink } from "../components/ui";

/** Shown for any unknown address. */
export function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-slate-50 p-6 text-center">
      <Logo className="size-12" />
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">Page not found</h1>
      <p className="text-slate-600">That page doesn&apos;t exist, or it has moved.</p>
      <ButtonLink to="/">Go to the home page</ButtonLink>
    </main>
  );
}
