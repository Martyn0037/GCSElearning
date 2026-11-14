// frontend/src/admin/AdminPage.test.tsx
/**
 * Covers:
 * - attention list explains each reason in plain words; empty state
 * - confirming sends board + tier; choosing a spec sends specificationId
 * - typed-in set texts can be matched to the board's list or removed
 * - topics covered: choose a subject, tick a topic, move a topic
 * - imported specifications table
 * - choosing a spec for a typed-in subject sends specificationId
 * - paging with "Next page"; update errors are shown
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AdminEnrolmentOut, AdminSpecificationOut, TopicMapOut } from "../api/generated/model";
import { CATALOGUE } from "../test/catalogue";
import type { Handler } from "../test/fakeApi";
import { installFakeApi, json, jsonBody } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const ADMIN = {
  id: "00000000-0000-4000-8000-000000000017",
  role: "admin",
  displayName: "Admin",
  username: null,
  email: "a@example.test",
  setupCompleted: false,
};

const SPECS: AdminSpecificationOut[] = [
  {
    id: "00000000-0000-4000-8000-000000000005",
    boardId: "00000000-0000-4000-8000-000000000002",
    code: "1MA1",
    title: "Maths",
    version: "Issue 2",
    tiered: true,
    subjectName: "Mathematics",
    boardName: "Pearson Edexcel",
    isCurrent: true,
    topicCount: 1,
    objectiveCount: 16,
    sourceFile: "specs/pearson-edexcel-1ma1.yaml",
  },
  {
    id: "00000000-0000-4000-8000-000000000006",
    boardId: "00000000-0000-4000-8000-000000000001",
    code: "8702",
    title: "English",
    version: "1.0",
    tiered: false,
    subjectName: "English Literature",
    boardName: "AQA",
    isCurrent: true,
    topicCount: 1,
    objectiveCount: 1,
    sourceFile: "specs/aqa-8702.yaml",
  },
];

const MATHS: AdminEnrolmentOut = {
  id: "00000000-0000-4000-8000-000000000008",
  subjectId: "00000000-0000-4000-8000-000000000003",
  subjectName: "Mathematics",
  isCustom: false,
  boardId: "00000000-0000-4000-8000-000000000002",
  boardName: "Pearson Edexcel",
  boardConfirmed: false,
  tier: "higher",
  tierConfirmed: false,
  status: "active",
  specification: SPECS[0]!,
  setTexts: [],
  studentId: "00000000-0000-4000-8000-000000000016",
  studentName: "Sam",
  attention: ["board_unconfirmed", "tier_unconfirmed"],
};

const ENGLISH: AdminEnrolmentOut = {
  ...MATHS,
  id: "00000000-0000-4000-8000-000000000010",
  subjectId: "00000000-0000-4000-8000-000000000004",
  subjectName: "English Literature",
  boardId: "00000000-0000-4000-8000-000000000001",
  boardName: "AQA",
  tier: null,
  boardConfirmed: true,
  tierConfirmed: true,
  specification: SPECS[1]!,
  attention: ["set_text_pending"],
  setTexts: [
    {
      id: "00000000-0000-4000-8000-000000000014",
      category: "Shakespeare play",
      optionId: null,
      title: "Macbth",
      author: null,
      status: "pending",
    },
  ],
};

const TOPICS: TopicMapOut = {
  enrolmentId: "00000000-0000-4000-8000-000000000008",
  subjectName: "Mathematics",
  tier: "higher",
  specification: SPECS[0]!,
  topics: [
    {
      id: "00000000-0000-4000-8000-000000000012",
      ref: "1",
      title: "Number",
      taughtAtSchool: false,
      unlocked: false,
      subtopics: [],
    },
    {
      id: "00000000-0000-4000-8000-000000000013",
      ref: "2",
      title: "Algebra",
      taughtAtSchool: false,
      unlocked: false,
      subtopics: [],
    },
  ],
};

function api(routes: Record<string, Handler | Handler[]> = {}, attention = [MATHS, ENGLISH]) {
  return installFakeApi({
    "GET /api/v1/users/me": () => json(ADMIN),
    "GET /api/v1/catalogue": () => json(CATALOGUE),
    "GET /api/v1/admin/specifications": () => json(SPECS),
    "GET /api/v1/admin/enrolments?attention=true&limit=25": () =>
      json({ items: attention, nextCursor: null }),
    "GET /api/v1/admin/enrolments?limit=100": () =>
      json({ items: [MATHS, ENGLISH], nextCursor: null }),
    ...routes,
  });
}

function bodyOf(init: RequestInit): unknown {
  return jsonBody(init);
}

describe("AdminPage", () => {
  it("should explain why each subject needs attention", async () => {
    api();
    renderApp("/admin");

    const card = (await screen.findByRole("heading", { name: "Sam: Mathematics" })).closest(
      "article",
    );
    expect(card).toHaveTextContent("Exam board not confirmed");
    expect(card).toHaveTextContent("Tier not confirmed");
  });

  it("should show an empty state when nothing needs attention", async () => {
    api({}, []);
    renderApp("/admin");

    expect(await screen.findByText(/Nothing needs your attention/)).toBeInTheDocument();
  });

  it("should confirm board and tier", async () => {
    let sent: unknown;
    api({
      "PATCH /api/v1/admin/enrolments/00000000-0000-4000-8000-000000000008": (init) => {
        sent = bodyOf(init);
        return json({ ...MATHS, attention: [] });
      },
    });
    renderApp("/admin");
    const card = (await screen.findByRole("heading", { name: "Sam: Mathematics" })).closest(
      "article",
    ) as HTMLElement;
    const user = userEvent.setup();

    await user.selectOptions(within(card).getByLabelText("Tier"), "Foundation");
    await user.click(within(card).getByRole("button", { name: "Confirm" }));

    await expect
      .poll(() => sent)
      .toEqual({ boardId: "00000000-0000-4000-8000-000000000002", tier: "foundation" });
  });

  it("should match a typed-in set text to the board's list", async () => {
    let sent: unknown;
    api({
      "PATCH /api/v1/admin/set-texts/00000000-0000-4000-8000-000000000014": (init) => {
        sent = bodyOf(init);
        return json(ENGLISH);
      },
    });
    renderApp("/admin");
    const user = userEvent.setup();

    await user.selectOptions(
      await screen.findByLabelText("Match Macbth to the board's list"),
      "Macbeth",
    );

    await expect.poll(() => sent).toEqual({ optionId: "00000000-0000-4000-8000-000000000007" });
  });

  it("should remove a typed-in set text", async () => {
    const fetchMock = api({
      "DELETE /api/v1/admin/set-texts/00000000-0000-4000-8000-000000000014": () =>
        new Response(null, { status: 204 }),
    });
    renderApp("/admin");

    const card = (await screen.findByRole("heading", { name: "Sam: English Literature" })).closest(
      "article",
    ) as HTMLElement;
    await userEvent.setup().click(within(card).getByRole("button", { name: "Remove" }));

    await expect
      .poll(() =>
        fetchMock.mock.calls.some(
          ([url]) => url === "/api/v1/admin/set-texts/00000000-0000-4000-8000-000000000014",
        ),
      )
      .toBe(true);
  });

  it("should tick a topic as covered and move a topic", async () => {
    // Arrange
    const sent: unknown[] = [];
    api({
      "GET /api/v1/admin/enrolments/00000000-0000-4000-8000-000000000008/topics": () =>
        json(TOPICS),
      "PUT /api/v1/admin/enrolments/00000000-0000-4000-8000-000000000008/topics/00000000-0000-4000-8000-000000000012":
        (init) => {
          sent.push(bodyOf(init));
          return json({
            ...TOPICS,
            topics: [{ ...TOPICS.topics[0]!, taughtAtSchool: true }, TOPICS.topics[1]!],
          });
        },
      "PUT /api/v1/admin/enrolments/00000000-0000-4000-8000-000000000008/topic-order": (init) => {
        sent.push(bodyOf(init));
        return json({ ...TOPICS, topics: [...TOPICS.topics].reverse() });
      },
    });
    renderApp("/admin");
    const user = userEvent.setup();

    // Act
    await user.selectOptions(await screen.findByLabelText("Subject"), "Sam: Mathematics");
    await user.click(await screen.findByRole("checkbox", { name: /Number: covered at school/ }));
    await expect.poll(() => sent.length).toBe(1);
    await user.click(screen.getByRole("button", { name: "Move Algebra up" }));

    // Assert
    await expect
      .poll(() => sent)
      .toEqual([
        { taughtAtSchool: true },
        {
          topicIds: [
            "00000000-0000-4000-8000-000000000013",
            "00000000-0000-4000-8000-000000000012",
          ],
        },
      ]);
  });

  it("should list imported specifications", async () => {
    api();
    renderApp("/admin");

    const table = await screen.findByRole("table");
    expect(within(table).getByText("1MA1")).toBeInTheDocument();
    expect(within(table).getByText("16")).toBeInTheDocument();
  });

  it("should send the chosen specification for a typed-in subject", async () => {
    let sent: unknown;
    const custom: AdminEnrolmentOut = {
      ...MATHS,
      id: "00000000-0000-4000-8000-000000000099",
      subjectId: null,
      subjectName: "More maths",
      isCustom: true,
      boardId: null,
      boardName: null,
      tier: null,
      status: "pending",
      specification: null,
      attention: ["no_specification"],
    };
    api(
      {
        "PATCH /api/v1/admin/enrolments/00000000-0000-4000-8000-000000000099": (init) => {
          sent = bodyOf(init);
          return json({ ...custom, attention: [] });
        },
      },
      [custom],
    );
    renderApp("/admin");
    const user = userEvent.setup();
    const card = (await screen.findByRole("heading", { name: /More maths/ })).closest(
      "article",
    ) as HTMLElement;

    await user.selectOptions(
      within(card).getByLabelText("Specification"),
      "Pearson Edexcel 1MA1 (Issue 2)",
    );
    await user.click(within(card).getByRole("button", { name: "Confirm" }));

    await expect.poll(() => sent).toEqual({ specificationId: SPECS[0]!.id });
    expect(within(card).getByLabelText("Exam board")).toHaveValue(SPECS[0]!.boardId);
  });

  it("should show the server's message when confirming fails", async () => {
    api({
      [`PATCH /api/v1/admin/enrolments/${MATHS.id}`]: () =>
        json({ error: { code: "INVALID_REQUEST", message: "Wrong board", traceId: null } }, 422),
    });
    renderApp("/admin");
    const card = (await screen.findByRole("heading", { name: "Sam: Mathematics" })).closest(
      "article",
    ) as HTMLElement;

    await userEvent.setup().click(within(card).getByRole("button", { name: "Confirm" }));

    expect(await within(card).findByRole("alert")).toHaveTextContent("Wrong board");
  });

  it("should page through the attention list", async () => {
    api({
      "GET /api/v1/admin/enrolments?attention=true&limit=25": () =>
        json({ items: [MATHS], nextCursor: "next" }),
      "GET /api/v1/admin/enrolments?attention=true&limit=25&cursor=next": () =>
        json({ items: [ENGLISH], nextCursor: null }),
    });
    renderApp("/admin");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Next page" }));

    expect(
      await screen.findByRole("heading", { name: "Sam: English Literature" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to start" }));
    expect(await screen.findByRole("heading", { name: "Sam: Mathematics" })).toBeInTheDocument();
  });
});
