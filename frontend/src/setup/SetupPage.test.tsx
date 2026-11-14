// frontend/src/setup/SetupPage.test.tsx
/**
 * Covers:
 * - first-time students are sent from home to /setup
 * - choosing a subject reveals board (with "I don't know" + most-schools hint),
 *   tier (tiered subjects only) and set-text fields
 * - set texts: picking from the board's list, or typing one in
 * - a board with no content shows the "still adding" note
 * - adding and removing a typed-in subject; duplicates ignored
 * - saving sends the right payload, then returns home; server errors shown
 * - the screen pre-fills from saved subjects
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MySubjectsOut, SubjectChoices } from "../api/generated/model";
import { CATALOGUE } from "../test/catalogue";
import { apiError, installFakeApi, json, jsonBody, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const NEW_STUDENT = { ...STUDENT, setupCompleted: false };
const NOTHING_SAVED: MySubjectsOut = { setupCompleted: false, subjects: [] };

function api(extra: Record<string, (init: RequestInit) => Response> = {}) {
  return installFakeApi({
    "GET /api/v1/users/me": () => json(NEW_STUDENT),
    "GET /api/v1/catalogue": () => json(CATALOGUE),
    "GET /api/v1/me/subjects": () => json(NOTHING_SAVED),
    ...extra,
  });
}

function sentBody(init: RequestInit): SubjectChoices {
  return jsonBody(init) as SubjectChoices;
}

describe("SetupPage", () => {
  it("should send a first-time student from home to setup", async () => {
    api();
    const { router } = renderApp("/");

    expect(
      await screen.findByRole("heading", { name: "Which subjects are you studying?" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/setup");
  });

  it("should show board, tier and the most-schools hint for a tiered subject", async () => {
    api();
    renderApp("/setup");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: "Mathematics" }));

    const board = screen.getByLabelText("Exam board");
    expect(board).toHaveValue("unknown");
    expect(
      within(board).getByRole("option", { name: "Pearson Edexcel (most schools)" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/We'll start with Pearson Edexcel/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Not sure" })).toBeChecked();
  });

  it("should not show tiers for an untiered subject but show its set texts", async () => {
    api();
    renderApp("/setup");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: "English Literature" }));

    expect(screen.queryByRole("radio", { name: "Higher" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Shakespeare play")).toBeInTheDocument();
    // No list on the spec for this category, so it's a free-text box.
    expect(screen.getByLabelText("19th-century novel (optional)")).toBeInTheDocument();
  });

  it("should note when a board has no content yet", async () => {
    api();
    renderApp("/setup");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Mathematics" }));

    await user.selectOptions(screen.getByLabelText("Exam board"), "AQA");

    expect(screen.getByText(/still adding this board's content/)).toBeInTheDocument();
  });

  it("should save chosen subjects, set texts and typed-in subjects, then go home", async () => {
    // Arrange
    let body: SubjectChoices | undefined;
    const saved: MySubjectsOut = { setupCompleted: true, subjects: [] };
    api({
      "PUT /api/v1/me/subjects": (init) => {
        body = sentBody(init);
        return json(saved);
      },
    });
    const { router } = renderApp("/setup");
    const user = userEvent.setup();

    // Act
    await user.click(await screen.findByRole("checkbox", { name: "Mathematics" }));
    await user.click(screen.getByRole("radio", { name: "Foundation" }));
    await user.click(screen.getByRole("checkbox", { name: "English Literature" }));
    await user.selectOptions(
      screen.getByLabelText("Shakespeare play"),
      "Macbeth — William Shakespeare",
    );
    await user.type(screen.getByLabelText("19th-century novel (optional)"), "A Christmas Carol");
    await user.type(
      screen.getByLabelText("Studying something that isn't listed?"),
      "Statistics{Enter}",
    );
    await user.click(screen.getByRole("button", { name: "Save my subjects" }));

    // Assert
    await screen.findByRole("heading", { name: "Hi Sam!" });
    expect(router.state.location.pathname).toBe("/");
    expect(body?.subjects).toEqual([
      {
        subjectId: "00000000-0000-4000-8000-000000000003",
        boardId: null,
        tier: "foundation",
        setTexts: [],
      },
      {
        subjectId: "00000000-0000-4000-8000-000000000004",
        boardId: null,
        tier: null,
        setTexts: [
          { category: "Shakespeare play", optionId: "00000000-0000-4000-8000-000000000007" },
          { category: "19th-century novel", customTitle: "A Christmas Carol" },
        ],
      },
      { customName: "Statistics", boardId: null, tier: null, setTexts: [] },
    ]);
  });

  it("should let a student type a set text not on the list", async () => {
    let body: SubjectChoices | undefined;
    api({
      "PUT /api/v1/me/subjects": (init) => {
        body = sentBody(init);
        return json({ setupCompleted: true, subjects: [] });
      },
    });
    renderApp("/setup");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "English Literature" }));

    await user.selectOptions(screen.getByLabelText("Shakespeare play"), "Something else (type it)");
    await user.type(screen.getByLabelText("Shakespeare play: type the title"), "Hamlet");
    await user.click(screen.getByRole("button", { name: "Save my subjects" }));

    await screen.findByRole("heading", { name: "Hi Sam!" });
    expect(body?.subjects[0]?.setTexts).toEqual([
      { category: "Shakespeare play", customTitle: "Hamlet" },
    ]);
  });

  it("should ignore a duplicate typed-in subject and allow removing one", async () => {
    api();
    renderApp("/setup");
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Studying something that isn't listed?");

    await user.type(input, "Statistics{Enter}");
    await user.type(input, " statistics {Enter}");
    expect(screen.getAllByText(/^Statistics/)).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Remove Statistics" }));
    expect(screen.queryByText(/^Statistics/)).not.toBeInTheDocument();
  });

  it("should disable saving until a subject is chosen", async () => {
    api();
    renderApp("/setup");

    expect(await screen.findByRole("button", { name: "Save my subjects" })).toBeDisabled();
  });

  it("should show the server's message when saving fails", async () => {
    api({
      "PUT /api/v1/me/subjects": () => apiError(422, "INVALID_REQUEST", "Unknown exam board"),
    });
    renderApp("/setup");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Mathematics" }));

    await user.click(screen.getByRole("button", { name: "Save my subjects" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown exam board");
  });

  it("should pre-fill from saved subjects", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(STUDENT),
      "GET /api/v1/catalogue": () => json(CATALOGUE),
      "GET /api/v1/me/subjects": () =>
        json({
          setupCompleted: true,
          subjects: [
            {
              id: "00000000-0000-4000-8000-000000000018",
              subjectId: "00000000-0000-4000-8000-000000000003",
              subjectName: "Mathematics",
              isCustom: false,
              boardId: "00000000-0000-4000-8000-000000000002",
              boardName: "Pearson Edexcel",
              boardConfirmed: true,
              tier: "higher",
              tierConfirmed: true,
              status: "active",
              specification: null,
              setTexts: [],
            },
          ],
        }),
    });
    renderApp("/setup");

    expect(await screen.findByRole("heading", { name: "Your subjects" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Mathematics" })).toBeChecked();
    expect(screen.getByLabelText("Exam board")).toHaveValue("00000000-0000-4000-8000-000000000002");
    expect(screen.getByRole("radio", { name: "Higher" })).toBeChecked();
  });

  it("should show an error when the catalogue can't load", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(NEW_STUDENT),
      "GET /api/v1/catalogue": () => apiError(500, "INTERNAL_ERROR"),
      "GET /api/v1/me/subjects": () => json(NOTHING_SAVED),
    });
    renderApp("/setup");

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the subject list");
  });
});
