// frontend/src/components/FullPageMessage.tsx
import type { ReactNode } from "react";

/** A centred status message (loading, errors). Announced to screen readers. */
export function FullPageMessage({
  children,
  busy = false,
}: {
  children: ReactNode;
  busy?: boolean;
}) {
  return (
    <main
      className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-slate-50 p-6 text-center text-slate-700"
      aria-busy={busy}
    >
      {busy && (
        <span
          aria-hidden="true"
          className="size-8 animate-spin rounded-full border-[3px] border-brand-200 border-t-brand-600"
        />
      )}
      <p role="status">{children}</p>
    </main>
  );
}
