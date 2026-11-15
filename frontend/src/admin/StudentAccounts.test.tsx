// frontend/src/admin/StudentAccounts.test.tsx
/**
 * Covers:
 * - edit details: name and username prefilled; only changed fields sent;
 *   username lower-cased; success message says the new username; list
 *   refreshed; unchanged form just closes; taken username (409) shown with
 *   the form kept open; invalid name/username explained, nothing sent;
 *   only one form open at a time
 * - detailsProblem: every rule, both boundaries
 * - lists students with their username, and marks a locked account
 * - happy path: typed password sent once, form closes, success message,
 *   list refreshed
 * - "Suggest one" fills both boxes with a visible, valid suggestion
 * - Show/Hide toggles the password boxes
 * - validation: too short and mismatched passwords are explained and
 *   nothing is sent
 * - server error message is shown; the form stays open
 * - Cancel closes the form without sending
 * - loading, load error and no-students states
 * - suggestion generator: format, valid length, rejection sampling to avoid
 *   modulo bias, and every branch of the problem checker
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AdminStudentOut } from "../api/generated/model";
import { apiError, installFakeApi, json, jsonBody } from "../test/fakeApi";
import { renderWithQuery } from "../test/renderWithQuery";
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  passwordProblem,
  suggestPassword,
} from "./passwordSuggestion";
import { StudentAccounts } from "./StudentAccounts";
import { detailsProblem } from "./studentDetails";

const SAM: AdminStudentOut = {
  id: "00000000-0000-4000-8000-0000000000b1",
  displayName: "Sam",
  username: "sam10",
  lockedUntil: null,
};
const LIST = "GET /api/v1/admin/students";
const RESET = `POST /api/v1/admin/students/${SAM.id}/password`;

async function openForm() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Reset password" }));
  return user;
}

describe("StudentAccounts: passwords", () => {
  it("should list students with their username and mark a locked account", async () => {
    // Arrange
    installFakeApi({
      [LIST]: () =>
        json([
          SAM,
          {
            ...SAM,
            id: "00000000-0000-4000-8000-0000000000b2",
            displayName: "Kit",
            lockedUntil: "2026-11-15T10:00:00Z",
          },
        ]),
    });

    // Act
    renderWithQuery(<StudentAccounts />);

    // Assert
    const sam = (await screen.findByText("Sam")).closest("li");
    const kit = screen.getByText("Kit").closest("li");
    expect(sam).toHaveTextContent("Signs in as sam10");
    expect(sam).not.toHaveTextContent("Locked");
    expect(kit).toHaveTextContent("Locked after wrong passwords");
  });

  it("should set a typed password, close the form and refresh the list", async () => {
    // Arrange
    const sent: unknown[] = [];
    const fetchMock = installFakeApi({
      [LIST]: () => json([SAM]),
      [RESET]: (init) => {
        sent.push(jsonBody(init));
        return new Response(null, { status: 204 });
      },
    });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act
    await user.type(screen.getByLabelText("New password"), "a-new-password");
    await user.type(screen.getByLabelText("Type it again"), "a-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));

    // Assert
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Sam's password has been changed and they've been signed out everywhere",
    );
    expect(sent).toEqual([{ newPassword: "a-new-password" }]);
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    const listCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/v1/admin/students");
    expect(listCalls).toHaveLength(2);
  });

  it("should fill both boxes with a visible suggestion", async () => {
    // Arrange
    installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act
    await user.click(screen.getByRole("button", { name: "Suggest one" }));

    // Assert
    const password = screen.getByLabelText("New password");
    expect(password).toHaveAttribute("type", "text");
    expect((password as HTMLInputElement).value).toMatch(/^[a-z]+-[a-z]+-[a-z]+-\d{2}$/);
    expect(screen.getByLabelText("Type it again")).toHaveValue(
      (password as HTMLInputElement).value,
    );
  });

  it("should show and hide the password", async () => {
    // Arrange
    installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act / Assert
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show" }));
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.getByLabelText("Type it again")).toHaveAttribute("type", "password");
  });

  it.each([
    ["short", "short", /at least 10 characters/],
    ["a-new-password", "a-different-one", /don't match/],
  ])("should explain a bad password (%s) and send nothing", async (first, second, message) => {
    // Arrange
    const fetchMock = installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act
    await user.type(screen.getByLabelText("New password"), first);
    await user.type(screen.getByLabelText("Type it again"), second);
    await user.click(screen.getByRole("button", { name: "Set new password" }));

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(screen.getByLabelText("New password")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("should show the server's message and keep the form open", async () => {
    // Arrange
    installFakeApi({
      [LIST]: () => json([SAM]),
      [RESET]: () => apiError(404, "RESOURCE_NOT_FOUND", "Student not found"),
    });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act
    await user.type(screen.getByLabelText("New password"), "a-new-password");
    await user.type(screen.getByLabelText("Type it again"), "a-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent("Student not found");
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
  });

  it("should close the form on Cancel without sending", async () => {
    // Arrange
    const fetchMock = installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openForm();

    // Act
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    // Assert
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should show loading, then an empty state when there are no students", async () => {
    installFakeApi({ [LIST]: () => json([]) });
    renderWithQuery(<StudentAccounts />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("No student accounts yet.")).toBeInTheDocument();
  });

  it("should say when the students can't be loaded", async () => {
    installFakeApi({ [LIST]: () => apiError(500, "INTERNAL") });
    renderWithQuery(<StudentAccounts />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the students.");
  });

  it("should name the form after the student", async () => {
    installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    await openForm();

    const form = screen.getByRole("form", { name: "Reset Sam's password" });
    expect(within(form).getByRole("button", { name: "Set new password" })).toBeEnabled();
  });
});

describe("password suggestions", () => {
  it("should make three words and two digits, long enough to be accepted", () => {
    // Act
    const passwords = Array.from({ length: 50 }, () => suggestPassword());

    // Assert
    for (const password of passwords) {
      expect(password).toMatch(/^[a-z]+-[a-z]+-[a-z]+-[1-9]\d$/);
      expect(passwordProblem(password, password)).toBeNull();
    }
  });

  it("should redraw values that would bias the choice", () => {
    // Arrange: 64 words divide 2^32 evenly, but 90 digit pairs don't, so the
    // top draw for the digits is above the unbiased limit and is redrawn.
    const draws = [0, 0, 0, 0xffff_ffff, 0];
    const random = (buffer: Uint32Array<ArrayBuffer>) => {
      buffer[0] = draws.shift() ?? 0;
      return buffer;
    };

    // Act
    const password = suggestPassword(random);

    // Assert: every pick is index 0 after the redraw
    expect(password).toBe("acorn-acorn-acorn-10");
    expect(draws).toEqual([]);
  });

  it.each([
    ["x".repeat(MIN_PASSWORD_LENGTH - 1), "x".repeat(MIN_PASSWORD_LENGTH - 1), /at least/],
    ["x".repeat(MAX_PASSWORD_LENGTH + 1), "x".repeat(MAX_PASSWORD_LENGTH + 1), /at most/],
    ["x".repeat(MIN_PASSWORD_LENGTH), "y".repeat(MIN_PASSWORD_LENGTH), /don't match/],
  ])("should explain what's wrong with %#", (password, confirm, message) => {
    expect(passwordProblem(password, confirm)).toMatch(message);
  });

  it("should accept a password of exactly the minimum and maximum length", () => {
    const shortest = "x".repeat(MIN_PASSWORD_LENGTH);
    const longest = "x".repeat(MAX_PASSWORD_LENGTH);
    expect(passwordProblem(shortest, shortest)).toBeNull();
    expect(passwordProblem(longest, longest)).toBeNull();
  });
});

const PATCH = `PATCH /api/v1/admin/students/${SAM.id}`;

async function openDetails() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Edit details" }));
  return user;
}

describe("StudentAccounts: details", () => {
  it("should prefill, send only what changed, and say the new username", async () => {
    // Arrange
    const sent: unknown[] = [];
    const fetchMock = installFakeApi({
      [LIST]: () => json([SAM]),
      [PATCH]: (init) => {
        sent.push(jsonBody(init));
        return json({ ...SAM, displayName: "Sam", username: "alex10" });
      },
    });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();
    const username = screen.getByLabelText("Username");

    // Act
    expect(screen.getByLabelText("Name")).toHaveValue("Sam");
    expect(username).toHaveValue("sam10");
    await user.clear(username);
    await user.type(username, " Alex10 ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Saved. Sam now signs in as alex10.",
    );
    expect(sent).toEqual([{ username: "alex10" }]);
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
    const listCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/v1/admin/students");
    expect(listCalls).toHaveLength(2);
  });

  it("should rename without touching the username", async () => {
    // Arrange
    const sent: unknown[] = [];
    installFakeApi({
      [LIST]: () => json([SAM]),
      [PATCH]: (init) => {
        sent.push(jsonBody(init));
        return json({ ...SAM, displayName: "Alex" });
      },
    });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "  Alex ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByRole("status")).toHaveTextContent("The app now calls them Alex.");
    expect(sent).toEqual([{ displayName: "Alex" }]);
  });

  it("should just close when nothing changed", async () => {
    // Arrange
    const fetchMock = installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should show a taken username and keep the form open", async () => {
    // Arrange
    installFakeApi({
      [LIST]: () => json([SAM]),
      [PATCH]: () => apiError(409, "USERNAME_TAKEN", "That username is already taken."),
    });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act
    await user.clear(screen.getByLabelText("Username"));
    await user.type(screen.getByLabelText("Username"), "kit10");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent("That username is already taken.");
    expect(screen.getByLabelText("Username")).toHaveValue("kit10");
  });

  it.each([
    ["Name", "", /Enter a name/],
    ["Username", "al", /3–32 lower-case letters/],
  ])("should explain a bad %s and send nothing", async (field, value, message) => {
    // Arrange
    const fetchMock = installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act
    await user.clear(screen.getByLabelText(field));
    if (value) await user.type(screen.getByLabelText(field), value);
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should cancel without sending, and open one form at a time", async () => {
    // Arrange
    const fetchMock = installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act / Assert: the other actions are hidden while a form is open
    expect(screen.queryByRole("button", { name: "Reset password" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset password" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["the network is down", () => Promise.reject(new TypeError("down")), /Can't reach the server/],
    [
      "the reply is malformed",
      () => json({ unexpected: true }),
      /Couldn't save the changes|unexpected/i,
    ],
  ])("should explain a failed save when %s", async (_case, handler, message) => {
    // Arrange
    installFakeApi({ [LIST]: () => json([SAM]), [PATCH]: handler });
    renderWithQuery(<StudentAccounts />);
    const user = await openDetails();

    // Act
    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
  });
});

describe("detailsProblem", () => {
  it.each([
    ["  ", "sam10", /Enter a name/],
    ["x".repeat(41), "sam10", /at most 40/],
    ["Al\u0007ex", "sam10", /can't be used/],
    ["Alex", "ab", /lower-case/],
    ["Alex", "x".repeat(33), /lower-case/],
    ["Alex", "-alex", /lower-case/],
    ["Alex", "alex@example.com", /lower-case/],
  ])("should reject name %j / username %j", (name, username, message) => {
    expect(detailsProblem(name, username)).toMatch(message);
  });

  it.each([
    ["A", "abc"],
    ["x".repeat(40), "x".repeat(32)],
    [" Alex ", " Alex.K_10 "],
  ])("should accept name %j / username %j", (name, username) => {
    expect(detailsProblem(name, username)).toBeNull();
  });
});
