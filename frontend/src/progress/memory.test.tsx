// frontend/src/progress/memory.test.tsx
/**
 * Covers:
 * - wrong answer: "Where it went wrong" appears once the explanation is ready
 *   (polling while pending); nothing extra when unavailable
 * - "Try a similar one" loads another question; its error is shown
 * - reviews: home shows "Review N mistakes"; review page shows the review
 *   badge, the "fixed" message, and "All caught up" when nothing is due
 * - My mistakes: topic/misconception summary, open list with answers,
 *   explanation and next review date, "Show more" paging, Fixed tab
 * - Progress: topic mastery bars, activity table, strongest/weakest skills,
 *   empty activity message
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type {
  AnswerResultOut,
  MistakeOut,
  PracticeItemOut,
  ProgressOut,
} from "../api/generated/model";
import type { Handler } from "../test/fakeApi";
import { apiError, installFakeApi, json, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const ENROLMENT = "00000000-0000-4000-8000-0000000000e1";
const TOPIC = "00000000-0000-4000-8000-0000000000a1";
const ITEM = "00000000-0000-4000-8000-0000000000f1";
const ITEM2 = "00000000-0000-4000-8000-0000000000f2";
const MISTAKE = "00000000-0000-4000-8000-0000000000d1";
const NEXT = `POST /api/v1/practice/enrolments/${ENROLMENT}/topics/${TOPIC}/next`;

const ITEM_OUT: PracticeItemOut = {
  id: ITEM,
  questionType: "multiple_choice",
  commandWord: "Write down",
  stem: "Write down the HCF of 12 and 18.",
  options: [
    { label: "A", text: "2" },
    { label: "B", text: "3" },
    { label: "C", text: "6" },
    { label: "D", text: "36" },
  ],
  unit: null,
  marks: 1,
  difficulty: 1,
  objectiveRef: "N4",
  hints: [],
  hintsRemaining: 4,
  review: false,
  keypad: false,
  symbolKeys: [],
};

const WRONG: AnswerResultOut = {
  itemId: ITEM,
  correct: false,
  assisted: false,
  correctAnswer: "C: 6",
  workedSolution: "HCF is 6.",
  levelBefore: 1,
  levelAfter: 1,
  mistakeId: MISTAKE,
  review: false,
  mistakeResolved: false,
};

const MISTAKE_OUT: MistakeOut = {
  id: MISTAKE,
  enrolmentId: ENROLMENT,
  subjectName: "Mathematics",
  topicId: TOPIC,
  topicRef: "1",
  topicTitle: "Number",
  objectiveRef: "N4",
  questionStem: "Write down the HCF of 12 and 18.",
  options: ITEM_OUT.options,
  studentAnswer: "A",
  correctAnswer: "C: 6",
  workedSolution: "HCF is 6.",
  explanation: "You picked 2, a common factor but not the highest.",
  explanationStatus: "ready",
  misconception: "picks a common factor, not the highest",
  assisted: false,
  nextReviewOn: "2026-11-15",
  resolved: false,
  createdAt: "2026-11-14T12:00:00Z",
};

function api(routes: Record<string, Handler | Handler[]>) {
  return installFakeApi({ "GET /api/v1/users/me": () => json(STUDENT), ...routes });
}

async function answerWrongly() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("radio", { name: /A\s*2/ }));
  await user.click(screen.getByRole("button", { name: "Check answer" }));
  await screen.findByText("✗ Not quite");
  return user;
}

describe("after a wrong answer", () => {
  it("should show where it went wrong once the explanation is ready", async () => {
    api({
      [NEXT]: () => json(ITEM_OUT),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => json(WRONG),
      [`GET /api/v1/me/mistakes/${MISTAKE}`]: [
        () => json({ ...MISTAKE_OUT, explanation: null, explanationStatus: "pending" }),
        () => json(MISTAKE_OUT),
      ],
    });
    renderApp(`/practice/${ENROLMENT}/${TOPIC}`);
    await answerWrongly();

    expect(await screen.findByText("Working out where it went wrong…")).toBeInTheDocument();
    const box = await screen.findByRole(
      "region",
      { name: "Where it went wrong" },
      { timeout: 4000 },
    );
    expect(box).toHaveTextContent("You picked 2");
    expect(box).toHaveTextContent("Common slip: picks a common factor");
  });

  it("should show nothing extra when no explanation is available", async () => {
    api({
      [NEXT]: () => json(ITEM_OUT),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => json(WRONG),
      [`GET /api/v1/me/mistakes/${MISTAKE}`]: () =>
        json({ ...MISTAKE_OUT, explanation: null, explanationStatus: "unavailable" }),
    });
    renderApp(`/practice/${ENROLMENT}/${TOPIC}`);
    await answerWrongly();

    expect(await screen.findByText("HCF is 6.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Where it went wrong" })).not.toBeInTheDocument();
  });

  it("should load a similar question, and show why when there isn't one", async () => {
    api({
      [NEXT]: () => json(ITEM_OUT),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => json(WRONG),
      [`GET /api/v1/me/mistakes/${MISTAKE}`]: () => json(MISTAKE_OUT),
      [`POST /api/v1/practice/items/${ITEM}/similar`]: [
        () => apiError(409, "QUESTIONS_PREPARING", "x"),
        () => json({ ...ITEM_OUT, id: ITEM2, stem: "Write down the HCF of 8 and 12." }),
      ],
    });
    renderApp(`/practice/${ENROLMENT}/${TOPIC}`);
    const user = await answerWrongly();

    await user.click(screen.getByRole("button", { name: "Try a similar one" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("preparing questions");
    await user.click(screen.getByRole("button", { name: "Try a similar one" }));

    expect(await screen.findByText("Write down the HCF of 8 and 12.")).toBeInTheDocument();
  });
});

describe("reviews", () => {
  it("should offer due reviews on the home page", async () => {
    api({
      "GET /api/v1/me/subjects": () => json({ setupCompleted: true, subjects: [] }),
      "GET /api/v1/me/reviews/summary": () => json({ dueToday: 2, nextDueOn: null }),
    });
    renderApp("/");

    expect(await screen.findByRole("link", { name: /Review 2 mistakes/ })).toHaveAttribute(
      "href",
      "/review",
    );
  });

  it("should mark review questions and celebrate a fix", async () => {
    api({
      "POST /api/v1/practice/reviews/next": () => json({ ...ITEM_OUT, review: true }),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () =>
        json({ ...WRONG, correct: true, review: true, mistakeResolved: true }),
    });
    renderApp("/review");
    const user = userEvent.setup();

    expect(await screen.findByText("Review: you got this one wrong before")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /C\s*6/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText(/Fixed! You won't see this mistake again/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try a similar one" })).not.toBeInTheDocument();
  });

  it("should say when everything is reviewed", async () => {
    api({ "POST /api/v1/practice/reviews/next": () => apiError(409, "NO_REVIEWS_DUE", "x") });
    renderApp("/review");

    expect(await screen.findByText("All caught up for today. ✓")).toBeInTheDocument();
  });
});

describe("My mistakes", () => {
  it("should summarise by topic and list mistakes with paging and a fixed tab", async () => {
    api({
      "GET /api/v1/me/mistakes/summary": () =>
        json([
          {
            enrolmentId: ENROLMENT,
            subjectName: "Mathematics",
            topicId: TOPIC,
            topicRef: "1",
            topicTitle: "Number",
            open: 2,
            fixed: 1,
            misconceptions: [{ label: "picks a common factor, not the highest", count: 2 }],
          },
        ]),
      "GET /api/v1/me/mistakes?fixed=false&limit=20": () =>
        json({ items: [MISTAKE_OUT], nextCursor: "next" }),
      "GET /api/v1/me/mistakes?fixed=false&limit=20&cursor=next": () =>
        json({
          items: [{ ...MISTAKE_OUT, id: ITEM2, questionStem: "Second mistake" }],
          nextCursor: null,
        }),
      "GET /api/v1/me/mistakes?fixed=true&limit=20": () =>
        json({ items: [{ ...MISTAKE_OUT, resolved: true, nextReviewOn: null }], nextCursor: null }),
    });
    renderApp("/mistakes");
    const user = userEvent.setup();

    const summary = await screen.findByRole("region", { name: "Mistakes by topic" });
    expect(summary).toHaveTextContent("2 to fix · 1 fixed");
    expect(
      within(summary).getByText(/picks a common factor, not the highest ×2/),
    ).toBeInTheDocument();
    const card = (
      await screen.findByText("You picked 2, a common factor but not the highest.")
    ).closest("article")!;
    expect(card).toHaveTextContent("Back for review on Sun 15 Nov");
    await user.click(screen.getByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Second mistake")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Fixed" }));
    expect(await screen.findByText("✓ Fixed")).toBeInTheDocument();
  });
});

describe("Progress", () => {
  const PROGRESS: ProgressOut = {
    enrolmentId: ENROLMENT,
    subjectName: "Mathematics",
    topics: [
      {
        topicId: TOPIC,
        ref: "1",
        title: "Number",
        mastery: 0.62,
        objectivesTotal: 16,
        objectivesPractised: 3,
        attempts: 10,
        accuracy: 0.7,
      },
    ],
    daily: Array.from({ length: 30 }, (_, i) => ({
      date: `2026-10-${String(i + 1).padStart(2, "0")}`,
      attempts: i === 29 ? 5 : 0,
      correct: i === 29 ? 3 : 0,
    })),
    strongest: [{ ref: "N4", text: "prime numbers", mastery: 0.9, attempts: 6 }],
    weakest: [{ ref: "N9", text: "standard form $A \\times 10^{n}$", mastery: 0.3, attempts: 4 }],
  };

  it("should show topic mastery, activity and skills", async () => {
    api({ [`GET /api/v1/me/subjects/${ENROLMENT}/progress`]: () => json(PROGRESS) });
    renderApp(`/progress/${ENROLMENT}`);

    const bar = await screen.findByRole("progressbar", { name: "Number mastery" });
    expect(bar).toHaveAttribute("aria-valuenow", "62");
    expect(screen.getByText(/3 of 16 skills practised · 70% right/)).toBeInTheDocument();
    expect(screen.getByText("5 answers in the last 30 days.")).toBeInTheDocument();
    const row = screen.getByRole("cell", { name: "30 Oct" }).closest("tr")!;
    expect(row).toHaveTextContent("30 Oct32");
    expect(screen.getByRole("region", { name: "Strongest skills" })).toHaveTextContent("N4");
    expect(screen.getByRole("region", { name: "Skills to work on" })).toHaveTextContent("N9");
  });

  it("should say when there's no recent activity", async () => {
    api({
      [`GET /api/v1/me/subjects/${ENROLMENT}/progress`]: () =>
        json({
          ...PROGRESS,
          daily: PROGRESS.daily.map((d) => ({ ...d, attempts: 0, correct: 0 })),
        }),
    });
    renderApp(`/progress/${ENROLMENT}`);

    expect(await screen.findByText("No answers in the last 30 days yet.")).toBeInTheDocument();
  });
});
