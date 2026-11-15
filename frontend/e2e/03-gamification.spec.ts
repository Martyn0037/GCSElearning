// frontend/e2e/03-gamification.spec.ts
/**
 * End-to-end: the home screen's Continue button, level and streak; today's
 * daily challenge played through to its summary; the badges page; and the
 * topic map's rings and boss battle status. Re-runnable: if today's
 * challenge is already done it checks the "done" state instead.
 *
 * Needs the same setup as 02-practice (Maths, topic 1 covered, E2E questions).
 */
import { expect, test } from "@playwright/test";

import { accounts, signIn } from "./accounts";

test("home dashboard, daily challenge, badges and rings", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("401")) problems.push(m.text());
  });
  await signIn(page, accounts.student());

  // Home: Continue first, then level and streak.
  await page.goto("/");
  await expect(page.getByRole("link", { name: /^Continue/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Level" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Streak" })).toBeVisible();

  const done = page.getByText(/Today's challenge done/);
  if (!(await done.isVisible())) {
    await page.getByRole("link", { name: /Daily challenge/ }).click();
    // Answer every question (option C is right in the fixtures) until the summary.
    for (let i = 0; i < 6; i += 1) {
      const summary = page.getByText("Daily challenge done!");
      const question = page.getByText(/^E2E: Write down/);
      await expect(summary.or(question)).toBeVisible();
      if (await summary.isVisible()) break;
      await page
        .locator("label")
        .filter({ has: page.getByRole("radio", { name: /^C/ }) })
        .click();
      await page.getByRole("button", { name: "Check answer" }).click();
      await page.getByRole("button", { name: /Next question|See results/ }).click();
    }
    await expect(page.getByText("Daily challenge done!")).toBeVisible();
    await page.getByRole("link", { name: "Back home" }).click();
  }
  await expect(page.getByText(/Today's challenge done/)).toBeVisible();

  // Badges page lists the catalogue.
  await page.getByRole("link", { name: /^Badges/ }).click();
  await expect(page.getByRole("heading", { name: "Badges" })).toBeVisible();
  await expect(page.getByText("Fixed 10 mistakes")).toBeVisible();

  // Topic map shows the ring and boss battle status for the covered topic.
  await page.goto("/");
  await page.getByRole("link", { name: /Mathematics/ }).click();
  await expect(page.getByText(/Boss battle/).first()).toBeVisible();

  expect(problems).toEqual([]); // includes CSP violations
});
