// frontend/src/auth/roles.ts
import type { Role } from "../api/generated/model";

/** Where each role lands after signing in. */
export const HOME_PATH_BY_ROLE: Record<Role, string> = {
  student: "/",
  guardian: "/guardian",
  admin: "/admin",
};

export function homePathForRole(role: Role): string {
  return HOME_PATH_BY_ROLE[role];
}
