// frontend/e2e/accounts.ts
// Test account credentials come from the environment, never from the repo.
import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} to run the end-to-end tests (see e2e/README.md)`);
  return value;
}

export const accounts = {
  student: () => ({
    id: required("E2E_STUDENT_USERNAME"),
    password: required("E2E_STUDENT_PASSWORD"),
  }),
  admin: () => ({ id: required("E2E_ADMIN_EMAIL"), password: required("E2E_ADMIN_PASSWORD") }),
};

/** Sign in through the real login form. */
export async function signIn(page: Page, account: { id: string; password: string }): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username or email").fill(account.id);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}
