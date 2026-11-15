// frontend/src/guardian/guardian.test.tsx
/**
 * Covers:
 * - guardian home: privacy-notice link, no consent prompt (ADR-021)
 * - weekly summary tiles, days practised, subjects with weak topics,
 *   achievements; earlier/later week navigation
 * - export downloads a JSON file
 * - deletion needs the password and DELETE; wrong password message; success
 *   refreshes
 * - no linked students; more than one student can be chosen
 * - privacy page is public and shows the version
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LinkedStudentOut, WeeklySummaryOut } from "../api/generated/model";
import { apiError, GUARDIAN, installFakeApi, json, jsonBody } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const STUDENT_ID = "00000000-0000-4000-8000-0000000000a9";
const BASE = `/api/v1/guardian/students/${STUDENT_ID}`;

const student = (granted: boolean): LinkedStudentOut => ({
  id: STUDENT_ID,
  displayName: "Sam",
  consent: granted
    ? { granted: true, policyVersion: "2026-11", grantedAt: "2026-11-15T10:00:00Z" }
    : { granted: false, policyVersion: null, grantedAt: null },
  currentPolicyVersion: "2026-11",
});

const WEEK: WeeklySummaryOut = {
  studentId: STUDENT_ID,
  displayName: "Sam",
  weekStart: "2026-11-09",
  weekEnd: "2026-11-15",
  answered: 20,
  correct: 15,
  minutes: 42,
  activeDays: ["2026-11-10", "2026-11-12"],
  xp: 340,
  streakDays: 3,
  mistakesFixed: 2,
  badges: ["Century"],
  bossBattles: [{ topicTitle: "Number", percent: 75 }],
  subjects: [
    {
      subjectName: "Mathematics",
      answered: 20,
      correct: 15,
      weakTopics: [{ title: "Algebra", mastery: 0.3, ring: "none" }],
    },
  ],
};

function api(routes: Parameters<typeof installFakeApi>[0]) {
  return installFakeApi({ "GET /api/v1/users/me": () => json(GUARDIAN), ...routes });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("guardian dashboard", () => {
  it("should show the week with a link to the privacy notice and no consent prompt", async () => {
    // Arrange
    api({
      "GET /api/v1/guardian/students": () => json([student(false)]),
      [`GET ${BASE}/summary?weeks_ago=0`]: () => json(WEEK),
    });

    // Act
    renderApp("/guardian");

    // Assert
    expect(await screen.findByRole("link", { name: "privacy notice" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(screen.queryByRole("button", { name: /agree/ })).not.toBeInTheDocument();
    expect(await screen.findByText("Questions answered")).toBeInTheDocument();
    expect(screen.getByText("Questions answered").nextSibling).toHaveTextContent("20");
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("42 min")).toBeInTheDocument();
    expect(
      within(screen.getByRole("list", { name: "Days practised" })).getAllByText("practised"),
    ).toHaveLength(2);
    expect(screen.getByText("Algebra")).toBeInTheDocument();
    expect(screen.getByText("Badge: Century")).toBeInTheDocument();
    expect(screen.getByText("Boss battle on Number: 75%")).toBeInTheDocument();
  });

  it("should move between weeks", async () => {
    api({
      "GET /api/v1/guardian/students": () => json([student(true)]),
      [`GET ${BASE}/summary?weeks_ago=0`]: () => json(WEEK),
      [`GET ${BASE}/summary?weeks_ago=1`]: () =>
        json({ ...WEEK, weekStart: "2026-11-02", answered: 4 }),
    });
    renderApp("/guardian");
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Week of 9 Nov" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Later ›" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "‹ Earlier" }));

    expect(await screen.findByRole("heading", { name: "Week of 2 Nov" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Later ›" }));
    expect(await screen.findByRole("heading", { name: "Week of 9 Nov" })).toBeInTheDocument();
  });

  it("should download the data as a JSON file", async () => {
    api({
      "GET /api/v1/guardian/students": () => json([student(true)]),
      [`GET ${BASE}/summary?weeks_ago=0`]: () => json(WEEK),
      [`GET ${BASE}/export`]: () => json({ student: { username: "sam10" } }),
    });
    const createUrl = vi.fn(() => "blob:x");
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }),
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderApp("/guardian");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Download all data (JSON)" }));

    await vi.waitFor(() => {
      expect(click).toHaveBeenCalled();
    });
    expect(createUrl).toHaveBeenCalled();
  });

  it("should delete only with the password and DELETE", async () => {
    // Arrange
    const fetchMock = api({
      "GET /api/v1/guardian/students": [() => json([student(true)]), () => json([])],
      [`GET ${BASE}/summary?weeks_ago=0`]: () => json(WEEK),
      [`POST ${BASE}/delete`]: [
        () => apiError(422, "WRONG_PASSWORD"),
        () => new Response(null, { status: 204 }),
      ],
    });
    renderApp("/guardian");
    const user = userEvent.setup();
    await user.click(await screen.findByText("Delete account permanently"));
    const button = screen.getByRole("button", { name: "Delete permanently" });

    // Act / Assert: needs both
    await user.type(screen.getByLabelText("Your password"), "wrong");
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("That password isn't right.");

    // Act / Assert: success
    await user.click(button);
    expect(
      await screen.findByText("No students are linked to your account yet."),
    ).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => url === `${BASE}/delete`);
    expect(jsonBody(call?.[1] ?? {})).toEqual({ confirm: "DELETE", password: "wrong" });
  });

  it("should let a guardian choose between students", async () => {
    const other = {
      ...student(true),
      id: "00000000-0000-4000-8000-0000000000b9",
      displayName: "Alex",
    };
    api({
      "GET /api/v1/guardian/students": () => json([student(true), other]),
      [`GET ${BASE}/summary?weeks_ago=0`]: () => json(WEEK),
      [`GET /api/v1/guardian/students/${other.id}/summary?weeks_ago=0`]: () =>
        json({ ...WEEK, studentId: other.id, displayName: "Alex", answered: 1 }),
    });
    renderApp("/guardian");
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("Student"), "Alex");

    expect(await screen.findByText("Alex's data")).toBeInTheDocument();
  });
});

describe("privacy page", () => {
  it("should be public and show the version", async () => {
    installFakeApi({ "GET /api/v1/users/me": () => apiError(401, "UNAUTHENTICATED") });
    renderApp("/privacy");
    expect(await screen.findByRole("heading", { name: "Privacy notice" })).toBeInTheDocument();
    expect(screen.getByText("Version 2026-11")).toBeInTheDocument();
    expect(screen.getByText(/never their name/)).toBeInTheDocument();
  });
});
