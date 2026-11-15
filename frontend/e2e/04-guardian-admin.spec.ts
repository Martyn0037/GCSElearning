// frontend/e2e/04-guardian-admin.spec.ts
/**
 * End-to-end: the guardian dashboard (weekly summary, export button)
 * and the admin tools (review queue, AI spend, grade boundaries, renaming
 * the student and resetting their password), with no
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

test("admin renames the student and resets their password; the student sees both", async ({
  browser,
}) => {
  const admin = await (await browser.newContext()).newPage();
  const problems = watchConsole(admin);
  await signIn(admin, accounts.admin());
  const student = accounts.student();

  // Set it to the same test password, so the other tests are unaffected.
  const row = admin.getByRole("listitem").filter({ hasText: `Signs in as ${student.id}` });
  const originalName = (await row.locator("p").first().textContent()) ?? "";

  // Rename (set back at the end, so the other tests are unaffected).
  await row.getByRole("button", { name: "Edit details" }).click();
  await row.getByLabel("Name", { exact: true }).fill("E2E Renamed");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(admin.getByText("Saved. The app now calls them E2E Renamed.")).toBeVisible();

  await row.getByRole("button", { name: "Reset password" }).click();
  await row.getByLabel("New password").fill(student.password);
  await row.getByLabel("Type it again").fill(student.password);
  await row.getByRole("button", { name: "Set new password" }).click();
  await expect(admin.getByText(/password has been changed/)).toBeVisible();

  const studentPage = await (await browser.newContext()).newPage();
  await signIn(studentPage, student);
  await expect(studentPage.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(studentPage.getByRole("heading", { name: "Hi E2E Renamed!" })).toBeVisible();

  await row.getByRole("button", { name: "Edit details" }).click();
  await row.getByLabel("Name", { exact: true }).fill(originalName);
  await row.getByRole("button", { name: "Save" }).click();
  await expect(admin.getByText(`Saved. The app now calls them ${originalName}.`)).toBeVisible();

  expect(problems).toEqual([]);
});
