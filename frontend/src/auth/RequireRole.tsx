// frontend/src/auth/RequireRole.tsx
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import type { Role, UserOut } from "../api/generated/model";
import { FullPageMessage } from "../components/FullPageMessage";
import { homePathForRole } from "./roles";
import { useSession } from "./useSession";

interface RequireRoleProps {
  /** Roles allowed to see the children. */
  roles: readonly Role[];
  children: (user: UserOut) => ReactNode;
}

/**
 * Route guard. Signed-out users go to /login (and come back afterwards);
 * users with another role go to their own home page.
 *
 * This only shapes the UI: the API enforces every permission itself.
 */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const session = useSession();
  const location = useLocation();

  switch (session.status) {
    case "loading":
      return <FullPageMessage busy>Loading…</FullPageMessage>;
    case "error":
      return <FullPageMessage>Something went wrong. Please refresh the page.</FullPageMessage>;
    case "signedOut":
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    case "signedIn":
      if (!roles.includes(session.user.role)) {
        return <Navigate to={homePathForRole(session.user.role)} replace />;
      }
      return <>{children(session.user)}</>;
  }
}
