// frontend/src/practice/learning.test.tsx
/**
 * Covers:
 * - written (extended) questions: a large box with a word count and the mark
 *   shown; keys insert at the cursor in the box; "Marking your answer…" while
 *   waiting; the result shows marks, level, points earned with AOs, feedback
 *   and the model answer; an unmarked answer shows the mark scheme without
 *   blame
 * - tutor: closed until opened; sends a message and shows the conversation;
 *   limit and unavailable errors; no box once no messages are left
 * - learn card: closed until opened; shows the explanation and worked
 *   example; "being written" message
 * - insertAt respects a longer limit for written answers
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AnswerResultOut, PracticeItemOut } from "../api/generated/model";
import { apiError, installFakeApi, json, STUDENT, type Handler } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";
import { insertAt } from "./editing";

const ENROLMENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const TOPIC = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ITEM = "00000000-0000-4000-8000-0000000000f1";
const NEXT = `POST /api/v1/practice/enrolments/${ENROLMENT}/topics/${TOPIC}/next`;
const ANSWER = `POST /api/v1/practice/items/${ITEM}/answer`;
const TUTOR = `/api/v1/practice/items/${ITEM}/tutor`;
const LEARN = `GET /api/v1/practice/items/${ITEM}/learn`;
const path = `/practice/${ENROLMENT}/${TOPIC}`;

const ESSAY_ITEM: PracticeItemOut = {
  id: ITEM,
  questionType: "extended",
  commandWord: "Explain",
  stem: "Explain why 1 is not a prime number.",
  options: [],
  unit: null,
  marks: 6,
  difficulty: 4,
  objectiveRef: "N4",
  hints: [],
  hintsRemaining: 4,
  review: false,
  keypad: false,
  symbolKeys: ["π", "√"],
};

const POINTS = [
  { text: "Defines a prime", marks: 2, ao: "AO1", awarded: true },
  { text: "Applies it to 1", marks: 2, ao: "AO2", awarded: true },
  { text: "Concludes", marks: 2, ao: "AO3", awarded: false },
];

function marked(overrides: Partial<AnswerResultOut> = {}): AnswerResultOut {
  return {
    itemId: ITEM,
    correct: false,
    assisted: false,
    correctAnswer: "A prime has exactly two factors; 1 has one, so it isn't prime.",
    workedSolution: "Use the definition.",
    levelBefore: 4,
    levelAfter: 4,
    mistakeId: null,
    review: false,
    mistakeResolved: false,
    marked: true,
    marking: {
      marks: 4,
      marksAvailable: 6,
      level: 2,
      levels: [{ level: 2, minMarks: 3, maxMarks: 4, descriptor: "Clear" }],
      points: POINTS,
      strengths: "You used the definition.",
      improvements: "Finish with a conclusion.",
    },
    ...overrides,
  };
}

function api(routes: Record<string, Handler | Handler[]>) {
  return installFakeApi({ "GET /api/v1/users/me": () => json(STUDENT), ...routes });
}

describe("written answers", () => {
  it("should take a long answer and show how it was marked", async () => {
    // Arrange
    let resolve: (r: Response) => void = () => undefined;
    api({
      [NEXT]: () => json(ESSAY_ITEM),
      [ANSWER]: () => new Promise<Response>((r) => (resolve = r)),
    });
    renderApp(path);
    const user = userEvent.setup();

    // Act: type, then add π at the cursor with a key
    const box = await screen.findByRole("textbox", { name: "Your answer" });
    await user.type(box, "One has one factor");
    (box as HTMLTextAreaElement).setSelectionRange(3, 3);
    await user.click(screen.getByRole("button", { name: "Pi" }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    // Assert: waiting
    expect(box.tagName).toBe("TEXTAREA");
    expect(box).toHaveValue("Oneπ has one factor");
    expect(screen.getByText("4 words")).toBeInTheDocument();
    expect(screen.getByText(/marked out of 6/)).toBeInTheDocument();
    expect(
      await screen.findByText(/Marking your answer against the mark scheme/),
    ).toBeInTheDocument();

    // Act: marking arrives
    resolve(json(marked()));

    // Assert: the breakdown
    expect(await screen.findByText("4 out of 6 marks")).toBeInTheDocument();
    expect(screen.getByText("Level 2")).toBeInTheDocument();
    expect(screen.getByText(/What went well:/)).toBeInTheDocument();
    expect(screen.getByText(/Next step:/)).toBeInTheDocument();
    expect(screen.getAllByText(/earned$/)).toHaveLength(3);
    expect(screen.getByText(/AO3, 2 marks/)).toBeInTheDocument();
    expect(screen.getByText("Model answer")).toBeInTheDocument();
    expect(screen.queryByText(/Correct answer:/)).not.toBeInTheDocument();
  });

  it("should show the mark scheme without blame when it couldn't be marked", async () => {
    api({
      [NEXT]: () => json(ESSAY_ITEM),
      [ANSWER]: () =>
        json(
          marked({
            marked: false,
            marking: {
              ...marked().marking!,
              marks: null,
              level: null,
              strengths: null,
              improvements: null,
            },
          }),
        ),
    });
    renderApp(path);
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "Your answer" }), "My answer");
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText(/We couldn't mark this one right now/)).toBeInTheDocument();
    expect(screen.getByText(/It won't count against you/)).toBeInTheDocument();
    expect(screen.queryByText("Not quite")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try a similar one" })).not.toBeInTheDocument();
  });

  it("should allow long answers when inserting keys", () => {
    const long = "a".repeat(300);
    expect(insertAt(long, "π", 300, 300, 4000).value).toHaveLength(301);
    expect(insertAt(long, "π", 300, 300).value).toHaveLength(300);
  });
});

describe("tutor", () => {
  const thread = (messages: { role: "student" | "tutor"; content: string }[], remaining = 10) => ({
    messages: messages.map((m, i) => ({
      id: `00000000-0000-4000-8000-00000000000${String(i)}`,
      createdAt: "2026-11-15T10:00:00Z",
      ...m,
    })),
    remaining,
  });

  it("should open, send a message and show the conversation", async () => {
    // Arrange
    api({
      [NEXT]: () => json(ESSAY_ITEM),
      [`GET ${TUTOR}`]: () => json(thread([])),
      [`POST ${TUTOR}`]: () =>
        json(
          thread(
            [
              { role: "student", content: "Where do I start?" },
              { role: "tutor", content: "What is a prime?" },
            ],
            11,
          ),
        ),
    });
    renderApp(path);
    const user = userEvent.setup();

    // Act
    await user.click(await screen.findByRole("button", { name: /Ask about this question/ }));
    await user.type(
      screen.getByRole("textbox", { name: "Your question for the tutor" }),
      "Where do I start?",
    );
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    expect(await screen.findByText("What is a prime?")).toBeInTheDocument();
    expect(screen.getByText("11 messages left for this question")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your question for the tutor" })).toHaveValue("");
  });

  it.each([
    ["TUTOR_LIMIT", /most messages for this question/],
    ["TUTOR_UNAVAILABLE", /isn't available right now/],
  ])("should explain %s", async (code, message) => {
    api({
      [NEXT]: () => json(ESSAY_ITEM),
      [`GET ${TUTOR}`]: () => json(thread([])),
      [`POST ${TUTOR}`]: () => apiError(409, code),
    });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Ask about this question/ }));
    await user.type(screen.getByRole("textbox", { name: "Your question for the tutor" }), "hi");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("should hide the box when no messages are left", async () => {
    api({ [NEXT]: () => json(ESSAY_ITEM), [`GET ${TUTOR}`]: () => json(thread([], 0)) });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Ask about this question/ }));

    expect(await screen.findByText("0 messages left for this question")).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Your question for the tutor" }),
    ).not.toBeInTheDocument();
  });
});

describe("learn card", () => {
  it("should show the explanation and worked example when opened", async () => {
    api({
      [NEXT]: () => json(ESSAY_ITEM),
      [LEARN]: () =>
        json({
          objectiveRef: "N4",
          objectiveText: "use the concepts of prime numbers",
          explanation: "A prime has exactly two factors.",
          workedExample: "$7$ has factors $1$ and $7$, so it is prime.",
        }),
    });
    renderApp(path);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Learn this skill/ }));

    expect(await screen.findByText("A prime has exactly two factors.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Worked example" })).toBeInTheDocument();
  });

  it.each([
    ["LEARN_PREPARING", /writing a learn card/],
    ["LEARN_UNAVAILABLE", /aren't available yet/],
  ])("should explain %s", async (code, message) => {
    api({ [NEXT]: () => json(ESSAY_ITEM), [LEARN]: () => apiError(409, code) });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Learn this skill/ }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });
});
