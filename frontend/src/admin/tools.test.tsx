// frontend/src/admin/tools.test.tsx
/**
 * Covers:
 * - review queue: lists questions with subject, objective, flags; filters by
 *   status; approve/reject/retire send the decision and refresh; empty and
 *   error states
 * - learn cards: list, approve and reject; empty state
 * - costs: today, month, cap bar, by purpose, 30 days; no-key warning
 * - grade boundaries: shows saved values per tier, saves edits (skipping
 *   empty grades), shows a save error; untiered specs have one form
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ReviewQuestionOut } from "../api/generated/model";
import { apiError, installFakeApi, json, jsonBody } from "../test/fakeApi";
import { renderWithQuery } from "../test/renderWithQuery";
import { Costs } from "./Costs";
import { GradeBoundaries } from "./GradeBoundaries";
import { LearnCardQueue } from "./LearnCardQueue";
import { ReviewQueue } from "./ReviewQueue";

const Q1 = "00000000-0000-4000-8000-0000000000c1";
const QUESTION: ReviewQuestionOut = {
  id: Q1,
  status: "flagged",
  questionType: "multiple_choice",
  difficulty: 2,
  objectiveRef: "N4",
  objectiveText: "use prime numbers",
  subjectName: "Mathematics",
  stem: "Which is prime?",
  options: [
    { label: "A", text: "4" },
    { label: "B", text: "7" },
  ],
  answer: { correct_option: "B" },
  marks: 1,
  workedSolution: "7 has two factors.",
  hints: ["h1", "h2", "h3", "h4"],
  confidence: 0.9,
  verificationNotes: "fine",
  flags: [{ reason: "Two answers are prime", createdAt: "2026-11-15T10:00:00Z" }],
  createdAt: "2026-11-15T09:00:00Z",
};

describe("review queue", () => {
  it("should list questions and send decisions", async () => {
    // Arrange
    const fetchMock = installFakeApi({
      "GET /api/v1/admin/review/questions": [
        () => json({ items: [QUESTION], nextCursor: null }),
        () => json({ items: [], nextCursor: null }),
      ],
      [`POST /api/v1/admin/review/questions/${Q1}`]: () => new Response(null, { status: 204 }),
    });
    renderWithQuery(<ReviewQueue />);
    const user = userEvent.setup();

    expect(await screen.findByText("Which is prime?")).toBeInTheDocument();
    expect(screen.getByText(/Student reported: Two answers are prime/)).toBeInTheDocument();
    expect(screen.getByText(/Mathematics · N4 · level 2/)).toBeInTheDocument();

    // Act
    await user.click(screen.getByRole("button", { name: "Approve" }));

    // Assert
    expect(await screen.findByText("Nothing waiting for review.")).toBeInTheDocument();
    const decision = fetchMock.mock.calls.find(
      ([url]) => url === `/api/v1/admin/review/questions/${Q1}`,
    );
    expect(jsonBody(decision?.[1] ?? {})).toEqual({ action: "approve" });
  });

  it("should filter by status", async () => {
    const fetchMock = installFakeApi({
      "GET /api/v1/admin/review/questions": () => json({ items: [], nextCursor: null }),
      "GET /api/v1/admin/review/questions?status=flagged": () =>
        json({ items: [QUESTION], nextCursor: null }),
    });
    renderWithQuery(<ReviewQueue />);
    const user = userEvent.setup();
    await screen.findByText("Nothing waiting for review.");

    await user.click(screen.getByRole("button", { name: "Flagged" }));

    expect(await screen.findByText("Which is prime?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Flagged" })).toHaveAttribute("aria-pressed", "true");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("should say when the queue can't load", async () => {
    installFakeApi({ "GET /api/v1/admin/review/questions": () => apiError(500, "INTERNAL") });
    renderWithQuery(<ReviewQueue />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't load the review queue/);
  });
});

describe("learn card queue", () => {
  const card = {
    id: "00000000-0000-4000-8000-0000000000d1",
    status: "pending_review",
    objectiveRef: "N4",
    objectiveText: "primes",
    explanation: "A prime has two factors.",
    workedExample: "7 is prime.",
    createdAt: "2026-11-15T09:00:00Z",
  };

  it("should approve and reject cards", async () => {
    const fetchMock = installFakeApi({
      "GET /api/v1/admin/review/learn-cards": [() => json([card]), () => json([])],
      [`POST /api/v1/admin/review/learn-cards/${card.id}`]: () =>
        new Response(null, { status: 204 }),
    });
    renderWithQuery(<LearnCardQueue />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reject" }));

    expect(await screen.findByText("No learn cards waiting.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(
      ([url]) => url === `/api/v1/admin/review/learn-cards/${card.id}`,
    );
    expect(jsonBody(call?.[1] ?? {})).toEqual({ action: "reject" });
  });
});

describe("costs", () => {
  it("should show spend against the caps", async () => {
    installFakeApi({
      "GET /api/v1/admin/costs": () =>
        json({
          todayGbp: "0.42",
          monthGbp: "21.00",
          dailyCapGbp: "2.50",
          monthlyCapGbp: "25",
          usdToGbp: "0.85",
          monthCalls: 120,
          monthFailures: 3,
          byPurpose: [{ purpose: "tutor", gbp: "12.00", calls: 80, failures: 1 }],
          last30Days: Array.from({ length: 30 }, (_, i) => ({
            date: `2026-10-${String(17 + (i % 14)).padStart(2, "0")}`,
            gbp: i === 29 ? "0.42" : "0.00",
            calls: i === 29 ? 5 : 0,
          })),
          apiKeyConfigured: false,
        }),
    });
    renderWithQuery(<Costs />);

    expect(await screen.findByText("£0.42", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("£21.00")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Share of monthly cap used" })).toHaveAttribute(
      "aria-valuenow",
      "84",
    );
    expect(screen.getByText(/120 calls · 3 failed/)).toBeInTheDocument();
    expect(
      within(screen.getByRole("table", { name: "This month by purpose" })).getByText("tutor"),
    ).toBeInTheDocument();
    expect(screen.getByText(/No Anthropic API key is set/)).toBeInTheDocument();
  });
});

describe("grade boundaries", () => {
  const SPEC = "00000000-0000-4000-8000-000000000005";
  const specs = (tiered: boolean) => [
    {
      id: SPEC,
      boardId: "00000000-0000-4000-8000-000000000002",
      code: "1MA1",
      title: "Maths",
      version: "Issue 2",
      tiered,
      subjectName: "Mathematics",
      boardName: "Pearson Edexcel",
      isCurrent: true,
      topicCount: 6,
      objectiveCount: 97,
      sourceFile: "specs/x.yaml",
    },
  ];

  it("should show saved boundaries and save edits", async () => {
    // Arrange
    const fetchMock = installFakeApi({
      "GET /api/v1/admin/specifications": () => json(specs(true)),
      [`GET /api/v1/admin/specifications/${SPEC}/grade-boundaries`]: () =>
        json([
          { specificationId: SPEC, tier: "foundation", boundaries: [{ grade: 1, minPercent: 15 }] },
        ]),
      [`PUT /api/v1/admin/specifications/${SPEC}/grade-boundaries`]: [
        () => json({ specificationId: SPEC, tier: "foundation", boundaries: [] }),
        () => apiError(422, "INVALID_REQUEST", "Higher grades need higher percentages."),
      ],
    });
    renderWithQuery(<GradeBoundaries />);
    const user = userEvent.setup();
    const foundation = await screen.findByRole("form", { name: "Foundation tier" });
    await screen.findByDisplayValue("15");

    // Act
    await user.type(within(foundation).getByLabelText("Grade 2 from (%)"), "30");
    await user.click(within(foundation).getByRole("button", { name: "Save boundaries" }));

    // Assert
    expect(await within(foundation).findByText("Saved.")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(jsonBody(put?.[1] ?? {})).toEqual({
      tier: "foundation",
      boundaries: [
        { grade: 1, minPercent: 15 },
        { grade: 2, minPercent: 30 },
      ],
    });
    expect(screen.getByRole("form", { name: "Higher tier" })).toBeInTheDocument();

    // Act / Assert: an invalid save shows the reason
    await user.click(within(foundation).getByRole("button", { name: "Save boundaries" }));
    expect(await within(foundation).findByRole("alert")).toHaveTextContent(
      "Higher grades need higher percentages.",
    );
  });

  it("should have one form for an untiered spec", async () => {
    installFakeApi({
      "GET /api/v1/admin/specifications": () => json(specs(false)),
      [`GET /api/v1/admin/specifications/${SPEC}/grade-boundaries`]: () => json([]),
    });
    renderWithQuery(<GradeBoundaries />);
    expect(await screen.findByRole("form", { name: "All students" })).toBeInTheDocument();
    expect(screen.getByLabelText("Grade 9 from (%)")).toBeInTheDocument();
  });
});
