// frontend/src/pages/LoginPage.test.tsx
/**
 * Covers:
 * - accessible form (labelled fields); submit disabled until both filled
 * - student lands on "/", guardian on "/guardian" after login
 * - returns to the page that redirected to login; ignores protocol-relative paths
 * - shows the server's error message on failure (role=alert)
 * - already signed-in users are sent home
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { apiError, GUARDIAN, installFakeApi, json, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const signedOut = {
  "GET /api/v1/users/me": () => apiError(401, "UNAUTHENTICATED"),
  "POST /api/v1/auth/refresh": () => apiError(401, "REFRESH_MISSING"),
};

async function fillAndSubmit(identifier = "sam10", password = "correct-horse") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Username or email"), identifier);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  it("should disable submit until both fields are filled", async () => {
    installFakeApi(signedOut);
    renderApp("/login");

    const button = await screen.findByRole("button", { name: "Sign in" });

    expect(button).toBeDisabled();
  });

  it("should send a student to their home page after signing in", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () =>
        json({ user: STUDENT, accessTokenExpiresAt: "2026-11-14T12:15:00Z" }),
    });
    const { router } = renderApp("/login");

    await fillAndSubmit();

    expect(await screen.findByRole("heading", { name: "Hi Sam!" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("should send a guardian to the guardian dashboard", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () =>
        json({ user: GUARDIAN, accessTokenExpiresAt: "2026-11-14T12:15:00Z" }),
    });
    const { router } = renderApp("/login");

    await fillAndSubmit("alex@example.test");

    expect(await screen.findByRole("heading", { name: "Progress dashboard" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/guardian");
  });

  it("should return to the page that sent the user to login", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () =>
        json({ user: GUARDIAN, accessTokenExpiresAt: "2026-11-14T12:15:00Z" }),
    });
    const { router } = renderApp("/login", { from: "/guardian" });

    await fillAndSubmit("alex@example.test");

    await screen.findByRole("heading", { name: "Progress dashboard" });
    expect(router.state.location.pathname).toBe("/guardian");
  });

  it("should ignore a protocol-relative redirect target", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () =>
        json({ user: STUDENT, accessTokenExpiresAt: "2026-11-14T12:15:00Z" }),
    });
    const { router } = renderApp("/login", { from: "//evil.example" });

    await fillAndSubmit();

    await screen.findByRole("heading", { name: "Hi Sam!" });
    expect(router.state.location.pathname).toBe("/");
  });

  it("should show the server's message when sign-in fails", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () => apiError(401, "INVALID_CREDENTIALS", "That didn't match."),
    });
    renderApp("/login");

    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent("That didn't match.");
  });

  it("should show a generic message for unexpected errors", async () => {
    installFakeApi({
      ...signedOut,
      "POST /api/v1/auth/login": () => Promise.reject(new Error("boom")),
    });
    renderApp("/login");

    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
  });

  it("should send an already signed-in student home", async () => {
    installFakeApi({ "GET /api/v1/users/me": () => json(STUDENT) });
    const { router } = renderApp("/login");

    await screen.findByRole("heading", { name: "Hi Sam!" });
    expect(router.state.location.pathname).toBe("/");
  });
});
