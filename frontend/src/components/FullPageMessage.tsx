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
      className="flex min-h-dvh items-center justify-center p-6 text-lg text-slate-700"
      aria-busy={busy}
    >
      <p role="status">{children}</p>
    </main>
  );
}
