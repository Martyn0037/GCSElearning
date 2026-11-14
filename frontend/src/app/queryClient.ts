// frontend/src/app/queryClient.ts
import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/http";

/** Don't retry errors that won't fix themselves (auth, validation, not found). */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

/** Create the app's query client with conservative defaults. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
