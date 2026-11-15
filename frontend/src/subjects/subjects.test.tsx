// frontend/src/subjects/subjects.test.tsx
/**
 * Covers:
 * - home lists subjects: active ones link to their topic map, pending ones
 *   show "Being set up"; board and tier shown; link to change subjects
 * - topic map: spec code/version/tier header, locked vs ready topics,
 *   skill counts, the "ask your parent" hint when everything is locked
 * - topic map errors: still being set up (409), not found (404)
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { EnrolmentOut, TopicMapOut } from "../api/generated/model";
import { apiError, installFakeApi, json, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";
import { NO_STANDING } from "../test/fixtures";

const MATHS: EnrolmentOut = {
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
  specification: {
    id: "00000000-0000-4000-8000-000000000011",
    boardId: "00000000-0000-4000-8000-000000000002",
    code: "1MA1",
    title: "Maths",
    version: "Issue 2 – June 2015",
    tiered: true,
  },
  setTexts: [],
};
const STATS: EnrolmentOut = {
  ...MATHS,
  id: "00000000-0000-4000-8000-000000000009",
  subjectId: null,
  subjectName: "Statistics",
  isCustom: true,
  boardId: null,
  boardName: null,
  tier: null,
  status: "pending",
  specification: null,
};

const MAP: TopicMapOut = {
  enrolmentId: "00000000-0000-4000-8000-000000000008",
  subjectName: "Mathematics",
  tier: "higher",
  specification: MATHS.specification!,
  topics: [
    {
      id: "00000000-0000-4000-8000-000000000012",
      ref: "1",
      title: "Number",
      taughtAtSchool: true,
      unlocked: true,
      standing: NO_STANDING,
      subtopics: [
        {
          id: "00000000-0000-4000-8000-000000000014",
          title: "Structure and calculation",
          objectiveCount: 9,
        },
      ],
    },
    {
      id: "00000000-0000-4000-8000-000000000013",
      ref: "2",
      title: "Algebra",
      taughtAtSchool: false,
      unlocked: false,
      standing: NO_STANDING,
      subtopics: [
        { id: "00000000-0000-4000-8000-000000000015", title: "Notation", objectiveCount: 1 },
      ],
    },
  ],
};

function api(map: () => Response = () => json(MAP)) {
  installFakeApi({
    "GET /api/v1/users/me": () => json(STUDENT),
    "GET /api/v1/me/subjects": () => json({ setupCompleted: true, subjects: [MATHS, STATS] }),
    "GET /api/v1/me/subjects/00000000-0000-4000-8000-000000000008/topics": map,
  });
}

describe("StudentHomePage", () => {
  it("should list active and pending subjects", async () => {
    api();
    renderApp("/");

    const maths = await screen.findByRole("link", { name: /Mathematics/ });
    expect(maths).toHaveAttribute("href", "/subjects/00000000-0000-4000-8000-000000000008");
    expect(maths).toHaveTextContent("Pearson Edexcel · Higher");
    expect(screen.getByText("Statistics").closest("div")).toHaveTextContent("Being set up");
    expect(screen.queryByRole("link", { name: /Statistics/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Change my subjects" })).toHaveAttribute(
      "href",
      "/setup",
    );
  });

  it("should open a subject's topic map", async () => {
    api();
    renderApp("/");

    await userEvent.setup().click(await screen.findByRole("link", { name: /Mathematics/ }));

    expect(await screen.findByRole("heading", { name: "Mathematics" })).toBeInTheDocument();
  });
});

describe("TopicMapPage", () => {
  it("should show the spec, ready and locked topics, and skill counts", async () => {
    api();
    renderApp("/subjects/00000000-0000-4000-8000-000000000008");

    expect(await screen.findByText("1MA1 · Issue 2 – June 2015 · Higher tier")).toBeInTheDocument();
    const number = screen.getByRole("heading", { name: "1. Number" }).closest("li");
    const algebra = screen.getByRole("heading", { name: "2. Algebra" }).closest("li");
    expect(number).toHaveTextContent("Ready");
    expect(number).toHaveTextContent("9 skills");
    expect(algebra).toHaveTextContent("Not covered yet");
    expect(algebra).toHaveTextContent("1 skill");
    expect(screen.queryByText(/Ask your parent/)).not.toBeInTheDocument();
  });

  it("should explain unlocking when every topic is locked", async () => {
    api(() =>
      json({
        ...MAP,
        topics: MAP.topics.map((t) => ({ ...t, unlocked: false, taughtAtSchool: false })),
      }),
    );
    renderApp("/subjects/00000000-0000-4000-8000-000000000008");

    expect(await screen.findByText(/Ask your parent or carer/)).toBeInTheDocument();
  });

  it("should say when a subject is still being set up", async () => {
    api(() => apiError(409, "SUBJECT_NOT_READY"));
    renderApp("/subjects/00000000-0000-4000-8000-000000000008");

    expect(await screen.findByRole("alert")).toHaveTextContent("still being set up");
  });

  it("should say when a subject isn't found", async () => {
    api(() => apiError(404, "RESOURCE_NOT_FOUND"));
    renderApp("/subjects/00000000-0000-4000-8000-000000000008");

    expect(await screen.findByRole("alert")).toHaveTextContent("couldn't find that subject");
  });

  it("should say when a subject has no topics yet", async () => {
    api(() => json({ ...MAP, topics: [] }));
    renderApp("/subjects/00000000-0000-4000-8000-000000000008");

    expect(await screen.findByText(/No topics have been added/)).toBeInTheDocument();
  });
});
