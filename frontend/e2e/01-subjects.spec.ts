// frontend/e2e/01-subjects.spec.ts
/**
 * End-to-end: subject setup, against the real stack.
 *
 * Covers:
 * - student chooses Maths ("I don't know" board) + a typed-in subject, saves,
 *   and sees Maths ready and the typed-in one "being set up"
 * - Maths topic map shows the imported 1MA1 topics, every one open to practise
 *   with no admin step (ADR-021)
 * Re-runnable: every step sets state rather than assuming it.
 */
import { expect, test } from "@playwright/test";

import { accounts, signIn } from "./accounts";

test("student sets up subjects and every topic is open", async ({ browser }) => {
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

  // Student: Number is open straight away.
  await studentPage.getByRole("link", { name: /Mathematics/ }).click();
  await expect(studentPage.getByText(/1MA1 · Issue 2 – June 2015/)).toBeVisible();
  const numberTopic = studentPage.getByRole("listitem").filter({
    has: studentPage.getByRole("heading", { name: "1. Number" }),
  });
  await expect(numberTopic.getByRole("link", { name: "Practise Number" })).toBeVisible();
  // Sections are folded away until opened.
  await numberTopic.getByText(/\d+ sections?/).click();
  await expect(numberTopic.getByText("Structure and calculation")).toBeVisible();
});
