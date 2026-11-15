// frontend/e2e/04-guardian-admin.spec.ts
/**
 * End-to-end: the guardian dashboard (weekly summary, export button)
 * and the admin tools (review queue, AI spend, grade boundaries), with no
 * console or security-policy errors. Re-runnable.
 */
import { expect, test } from "@playwright/test";

import { accounts, signIn } from "./accounts";

function watchConsole(page: import("@playwright/test").Page): string[] {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("401")) problems.push(m.text());
  });
  return problems;
}

test("guardian sees the week and their data controls, with no consent step", async ({ page }) => {
  const problems = watchConsole(page);
  await signIn(page, accounts.guardian());

  await expect(page.getByRole("heading", { name: "Progress dashboard" })).toBeVisible();
  await expect(page.getByText("Questions answered")).toBeVisible();
  await expect(page.getByRole("button", { name: /agree/ })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Days practised" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download all data (JSON)" })).toBeVisible();

  await page.getByRole("link", { name: "privacy notice" }).click();
  await expect(page.getByRole("heading", { name: "Privacy notice" })).toBeVisible();

  expect(problems).toEqual([]);
});

test("admin sees the review queue, AI spend and grade boundaries", async ({ page }) => {
  const problems = watchConsole(page);
  await signIn(page, accounts.admin());

  await expect(page.getByRole("heading", { name: "Review queue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI spend" })).toBeVisible();
  await expect(page.getByText(/This month/).first()).toBeVisible();
  await expect(
    page
      .getByRole("form", { name: "Foundation tier" })
      .or(page.getByRole("form", { name: "All students" }))
      .first(),
  ).toBeVisible();

  expect(problems).toEqual([]);
});
