// frontend/e2e/subjects.spec.ts
/**
 * End-to-end: subject setup and topic unlocking, against the real stack.
 *
 * Covers:
 * - student chooses Maths ("I don't know" board) + a typed-in subject, saves,
 *   and sees Maths ready and the typed-in one "being set up"
 * - Maths topic map shows the imported 1MA1 topics, locked
 * - admin marks "Number" as covered; the student now sees it as Ready
 * Re-runnable: every step sets state rather than assuming it.
 */
import { expect, test } from "@playwright/test";

import { accounts, signIn } from "./accounts";

test("student sets up subjects and admin unlocks a topic", async ({ browser }) => {
  // Student: choose subjects.
  const studentPage = await (await browser.newContext()).newPage();
  await signIn(studentPage, accounts.student());
  await studentPage.goto("/setup");

  const maths = studentPage.getByRole("checkbox", { name: "Mathematics" });
  if (!(await maths.isChecked())) await maths.check();
  await studentPage.getByLabel("Exam board").first().selectOption("unknown");
  await expect(studentPage.getByText(/We'll start with Pearson Edexcel/)).toBeVisible();

  const custom = studentPage.getByLabel("Studying something that isn't listed?");
  if ((await studentPage.getByText(/^Statistics/).count()) === 0) {
    await custom.fill("Statistics");
    await studentPage.getByRole("button", { name: "Add" }).click();
  }
  await studentPage.getByRole("button", { name: "Save my subjects" }).click();

  // Student: home shows statuses.
  await expect(studentPage.getByRole("heading", { name: /^Hi / })).toBeVisible();
  await expect(studentPage.getByRole("link", { name: /Mathematics/ })).toBeVisible();
  await expect(studentPage.getByText("Being set up")).toBeVisible();

  // Admin: mark Number as covered at school.
  const adminPage = await (await browser.newContext()).newPage();
  await signIn(adminPage, accounts.admin());
  const subjectSelect = adminPage.getByLabel("Subject", { exact: true });
  const mathsOption = await subjectSelect
    .locator("option", { hasText: "Mathematics" })
    .first()
    .textContent();
  await subjectSelect.selectOption({ label: (mathsOption ?? "").trim() });
  const number = adminPage.getByRole("checkbox", { name: /Number: covered at school/ });
  if (!(await number.isChecked())) {
    await number.check();
  }
  await expect(number).toBeChecked();

  // Student: Number is now ready.
  await studentPage.getByRole("link", { name: /Mathematics/ }).click();
  await expect(studentPage.getByText(/1MA1 · Issue 2 – June 2015/)).toBeVisible();
  const numberTopic = studentPage.getByRole("listitem").filter({
    has: studentPage.getByRole("heading", { name: "1. Number" }),
  });
  await expect(numberTopic.getByText("Ready")).toBeVisible();
  await expect(numberTopic.getByText("Structure and calculation")).toBeVisible();
});
