// frontend/src/practice/PracticePage.test.tsx
/**
 * Covers:
 * - loads a question (maths rendered), multiple-choice answer -> correct result,
 *   level-up message, then "Next question" loads another
 * - numeric answer shows unit and sends an Idempotency-Key; retrying after a
 *   failure reuses the same key
 * - "I'm stuck" reveals hints one by one; warning before the full solution
 * - wrong answer shows the correct answer and opens the worked solution
 * - "This looks wrong" sends the report and loads the next question
 * - friendly messages for QUESTIONS_PREPARING (with Try again) and TOPIC_LOCKED
 * - unlocked topics on the topic map link to practice
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AnswerResultOut, PracticeItemOut, TopicMapOut } from "../api/generated/model";
import type { Handler } from "../test/fakeApi";
import { apiError, installFakeApi, json, jsonBody, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const ENROLMENT = "00000000-0000-4000-8000-0000000000e1";
const TOPIC = "00000000-0000-4000-8000-0000000000a1";
const ITEM = "00000000-0000-4000-8000-0000000000f1";
const ITEM2 = "00000000-0000-4000-8000-0000000000f2";
const NEXT = `POST /api/v1/practice/enrolments/${ENROLMENT}/topics/${TOPIC}/next`;

const MCQ: PracticeItemOut = {
  id: ITEM,
  questionType: "multiple_choice",
  commandWord: "Write down",
  stem: "Write down the HCF of $12$ and $18$.",
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
};

const NUMERIC: PracticeItemOut = {
  ...MCQ,
  id: ITEM2,
  questionType: "numeric",
  stem: "Work out the length.",
  options: [],
  unit: "cm",
};

function result(overrides: Partial<AnswerResultOut> = {}): AnswerResultOut {
  return {
    itemId: ITEM,
    correct: true,
    assisted: false,
    correctAnswer: "C: 6",
    workedSolution: "Common factors are 1, 2, 3, 6.",
    levelBefore: 1,
    levelAfter: 1,
    mistakeId: null,
    review: false,
    mistakeResolved: false,
    ...overrides,
  };
}

function api(routes: Record<string, Handler | Handler[]>) {
  return installFakeApi({ "GET /api/v1/users/me": () => json(STUDENT), ...routes });
}

const practisePath = `/practice/${ENROLMENT}/${TOPIC}`;

describe("PracticePage", () => {
  it("should answer a multiple-choice question, level up and load the next", async () => {
    api({
      [NEXT]: [() => json(MCQ), () => json(NUMERIC)],
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => json(result({ levelAfter: 2 })),
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: /C\s*6/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText("✓ Correct!")).toBeInTheDocument();
    expect(screen.getByText(/Level up! You're now on level 2/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next question" }));
    expect(await screen.findByText("Work out the length.")).toBeInTheDocument();
  });

  it("should render maths in the question", async () => {
    api({ [NEXT]: () => json(MCQ) });
    const { container } = renderApp(practisePath);

    await screen.findByText(/Write down the HCF of/);

    expect(container.querySelectorAll("math").length).toBeGreaterThanOrEqual(2);
  });

  it("should send numeric answers with an idempotency key reused on retry", async () => {
    const keys: (string | null)[] = [];
    api({
      [NEXT]: () => json(NUMERIC),
      [`POST /api/v1/practice/items/${ITEM2}/answer`]: [
        (init) => {
          keys.push(new Headers(init.headers).get("Idempotency-Key"));
          return apiError(500, "INTERNAL_ERROR", "Something went wrong.");
        },
        (init) => {
          keys.push(new Headers(init.headers).get("Idempotency-Key"));
          expect(jsonBody(init)).toEqual({ answer: "7/2" });
          return json(result({ itemId: ITEM2 }));
        },
      ],
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    expect(await screen.findByText("cm")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your answer"), "7/2");
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText("✓ Correct!")).toBeInTheDocument();
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  it("should reveal hints one at a time and warn before the full solution", async () => {
    api({
      [NEXT]: () => json(MCQ),
      [`POST /api/v1/practice/items/${ITEM}/hints`]: [
        () => json({ ...MCQ, hints: ["Hint one"], hintsRemaining: 3 }),
        () => json({ ...MCQ, hints: ["Hint one", "Hint two", "Hint three"], hintsRemaining: 1 }),
      ],
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "I'm stuck" }));
    expect(await screen.findByText("Hint one")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Another hint" }));

    expect(await screen.findByRole("button", { name: "Show full solution" })).toBeInTheDocument();
    expect(screen.getByText(/won't count towards levelling up/)).toBeInTheDocument();
  });

  it("should show the correct answer and worked solution when wrong", async () => {
    api({
      [NEXT]: () => json(MCQ),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => json(result({ correct: false })),
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: /A\s*2/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText("✗ Not quite")).toBeInTheDocument();
    expect(screen.getByText(/Correct answer:/)).toHaveTextContent("C: 6");
    expect(screen.getByText("Common factors are 1, 2, 3, 6.")).toBeVisible();
  });

  it("should report a question and move on", async () => {
    let reported: unknown;
    api({
      [NEXT]: [() => json(MCQ), () => json(NUMERIC)],
      [`POST /api/v1/practice/items/${ITEM}/flag`]: (init) => {
        reported = jsonBody(init);
        return new Response(null, { status: 204 });
      },
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "🚩 This looks wrong" }));
    await user.type(screen.getByLabelText(/What looks wrong/), "Two answers fit");
    await user.click(screen.getByRole("button", { name: "Report and skip" }));

    expect(await screen.findByText("Work out the length.")).toBeInTheDocument();
    expect(reported).toEqual({ reason: "Two answers fit" });
  });

  it("should ask to wait when questions are being prepared, then retry", async () => {
    api({
      [NEXT]: [() => apiError(409, "QUESTIONS_PREPARING", "x"), () => json(MCQ)],
    });
    renderApp(practisePath);
    const user = userEvent.setup();

    expect(await screen.findByRole("alert")).toHaveTextContent("preparing questions");
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(/Write down the HCF/)).toBeInTheDocument();
  });

  it("should explain a locked topic", async () => {
    api({ [NEXT]: () => apiError(409, "TOPIC_LOCKED", "x") });
    renderApp(practisePath);

    expect(await screen.findByRole("alert")).toHaveTextContent("hasn't been marked as covered");
  });
});

describe("topic map practise links", () => {
  it("should link unlocked topics to practice", async () => {
    const map: TopicMapOut = {
      enrolmentId: ENROLMENT,
      subjectName: "Mathematics",
      tier: "higher",
      specification: {
        id: "00000000-0000-4000-8000-0000000000c1",
        boardId: "00000000-0000-4000-8000-0000000000c2",
        code: "1MA1",
        title: "Maths",
        version: "Issue 2",
        tiered: true,
      },
      topics: [
        {
          id: TOPIC,
          ref: "1",
          title: "Number",
          taughtAtSchool: true,
          unlocked: true,
          subtopics: [],
        },
        {
          id: "00000000-0000-4000-8000-0000000000a2",
          ref: "2",
          title: "Algebra",
          taughtAtSchool: false,
          unlocked: false,
          subtopics: [],
        },
      ],
    };
    api({ [`GET /api/v1/me/subjects/${ENROLMENT}/topics`]: () => json(map) });
    renderApp(`/subjects/${ENROLMENT}`);

    expect(await screen.findByRole("link", { name: "Practise Number" })).toHaveAttribute(
      "href",
      practisePath,
    );
    expect(screen.queryByRole("link", { name: "Practise Algebra" })).not.toBeInTheDocument();
  });
});
