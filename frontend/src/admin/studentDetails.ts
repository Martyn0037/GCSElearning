// frontend/src/admin/studentDetails.ts
/**
 * Checks for a student's name and username, matching the backend's rules
 * (``StudentUpdate`` in app/auth/schemas.py) so problems show before saving.
 */

export const MAX_DISPLAY_NAME_LENGTH = 40;
export const MAX_USERNAME_LENGTH = 32;
const USERNAME = /^[a-z0-9][a-z0-9._-]{2,31}$/;
// eslint-disable-next-line no-control-regex -- control characters are exactly what's rejected
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

/**
 * Why the name or username can't be saved, or null if both are fine.
 *
 * Args:
 *   name: The display name as typed.
 *   username: The username as typed (case and outer spaces are ignored).
 */
export function detailsProblem(name: string, username: string): string | null {
  const cleanName = name.trim();
  if (!cleanName) return "Enter a name.";
  if (cleanName.length > MAX_DISPLAY_NAME_LENGTH) {
    return `Use at most ${String(MAX_DISPLAY_NAME_LENGTH)} characters for the name.`;
  }
  if (CONTROL_CHARS.test(cleanName)) return "The name contains characters that can't be used.";
  if (!USERNAME.test(username.trim().toLowerCase())) {
    return "Usernames are 3–32 lower-case letters, numbers, dots, hyphens or underscores, starting with a letter or number.";
  }
  return null;
}
