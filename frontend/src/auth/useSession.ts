// frontend/src/auth/useSession.ts
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { logout as logoutRequest, useGetCurrentUser } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";

export type SessionState =
  | { status: "loading" }
  | { status: "signedOut" }
  | { status: "signedIn"; user: UserOut }
  | { status: "error"; error: Error };

/**
 * The current session, derived from `GET /users/me`.
 *
 * A 401 (after the HTTP client's one refresh attempt) means "signed out",
 * not an error.
 */
export function useSession(): SessionState {
  const query = useGetCurrentUser({ query: { retry: false, staleTime: 5 * 60_000 } });
  if (query.isPending) return { status: "loading" };
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 401) {
      return { status: "signedOut" };
    }
    return { status: "error", error: query.error };
  }
  return { status: "signedIn", user: query.data };
}

/**
 * Sign out on the server, then forget all cached data for this user.
 *
 * Never rejects: if the server can't be reached, the local session is still
 * cleared so this user's data doesn't stay on screen (the refresh token
 * expires on its own).
 */
export function useSignOut(): () => Promise<void> {
  const queryClient = useQueryClient();
  return useCallback(async () => {
    try {
      await logoutRequest();
    } catch (error) {
      console.warn("Sign-out request failed; cleared the local session anyway", error);
    } finally {
      queryClient.clear();
    }
  }, [queryClient]);
}
