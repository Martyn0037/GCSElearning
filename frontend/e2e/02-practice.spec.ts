// frontend/e2e/02-practice.spec.ts
/**
 * End-to-end: the brief's core flow against the real stack.
 * login -> open a topic -> answer -> "I'm stuck" -> hint -> wrong answer ->
 * see the correct answer and worked solution -> next question -> the mistake
 * is on "My mistakes" -> the progress page renders.
 *
 * Needs the E2E fixture questions (app.cli.seed_test_questions for 1MA1 N4),
 * Maths on the student's subjects, and topic 1 covered (01-subjects.spec does that).
 */
import { expect, test } from "@playwright/test";

import { accounts, signIn } from "./accounts";

test("student answers, asks for a hint, gets one wrong and moves on", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => {
    // A 401 for /users/me before signing in is expected.
    if (m.type() === "error" && !m.text().includes("401")) problems.push(m.text());
  });
  await signIn(page, accounts.student());

  // Make sure Maths is chosen (re-runnable), then open its topic map.
  await page.goto("/setup");
  const maths = page.getByRole("checkbox", { name: "Mathematics" });
  if (!(await maths.isChecked())) await maths.check();
  await page.getByRole("button", { name: "Save my subjects" }).click();
  await page.getByRole("link", { name: /Mathematics/ }).click();

  await page.getByRole("link", { name: "Practise Number" }).click();
  const question = page.getByText(/^E2E: Write down/);
  await expect(question).toBeVisible();

  // Stuck: ask for a hint. (A previous run may have left this question open
  // with a hint already showing, so the button may say "Another hint".)
  await page.getByRole("button", { name: /I'm stuck|Another hint/ }).click();
  await expect(page.getByText("E2E hint 1")).toBeVisible();

  // Answer wrongly: option A is never correct in the fixtures.
  // Tap the option as a person would (the radio input itself is visually hidden).
  await page
    .locator("label")
    .filter({ has: page.getByRole("radio", { name: /^A/ }) })
    .click();
  await expect(page.getByRole("radio", { name: /^A/ })).toBeChecked();
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("✗ Not quite")).toBeVisible();
  await expect(page.getByText(/Correct answer:/)).toBeVisible();
  await expect(page.getByText("E2E fixture worked solution.")).toBeVisible();

  // Next question.
  await page.getByRole("button", { name: "Next question" }).click();
  await expect(page.getByText(/^E2E: Write down/)).toBeVisible();

  // The mistake is waiting on "My mistakes", with a review date.
  await page.goto("/mistakes");
  await expect(page.getByRole("region", { name: "Mistakes by topic" })).toContainText("Number");
  await expect(page.getByText(/Back for review on/).first()).toBeVisible();

  // Progress page renders its chart without errors.
  await page.goto("/");
  await page.getByRole("link", { name: /Mathematics/ }).click();
  await page.getByRole("link", { name: "Progress" }).click();
  await expect(page.getByRole("progressbar", { name: "Number mastery" })).toBeVisible();
  await expect(page.getByText(/answers in the last 30 days/)).toBeVisible();

  expect(problems).toEqual([]); // includes CSP violations
});
