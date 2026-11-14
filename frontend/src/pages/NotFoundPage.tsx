// frontend/src/pages/NotFoundPage.tsx
import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <Link to="/" className="text-brand-700 underline">
        Go to the home page
      </Link>
    </main>
  );
}
