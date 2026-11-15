// frontend/src/admin/StudentPasswords.test.tsx
/**
 * Covers:
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
import { StudentPasswords } from "./StudentPasswords";

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

describe("StudentPasswords", () => {
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
    renderWithQuery(<StudentPasswords />);

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
    renderWithQuery(<StudentPasswords />);
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
    renderWithQuery(<StudentPasswords />);
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
    renderWithQuery(<StudentPasswords />);
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
    renderWithQuery(<StudentPasswords />);
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
    renderWithQuery(<StudentPasswords />);
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
    renderWithQuery(<StudentPasswords />);
    const user = await openForm();

    // Act
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    // Assert
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should show loading, then an empty state when there are no students", async () => {
    installFakeApi({ [LIST]: () => json([]) });
    renderWithQuery(<StudentPasswords />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("No student accounts yet.")).toBeInTheDocument();
  });

  it("should say when the students can't be loaded", async () => {
    installFakeApi({ [LIST]: () => apiError(500, "INTERNAL") });
    renderWithQuery(<StudentPasswords />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the students.");
  });

  it("should name the form after the student", async () => {
    installFakeApi({ [LIST]: () => json([SAM]) });
    renderWithQuery(<StudentPasswords />);
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
