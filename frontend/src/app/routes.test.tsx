// frontend/src/app/routes.test.tsx
/**
 * Covers:
 * - signed-out users are sent to /login from protected pages
 * - users visiting another role's page are sent to their own home
 * - admin page renders for admins; unknown paths show "Page not found"
 * - a server error while loading the session shows an error, not a redirect
 * - sign out calls the API, clears the session and returns to /login,
 *   even if the logout request fails
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { apiError, installFakeApi, json, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const ADMIN = {
  ...STUDENT,
  id: "33333333-3333-4333-8333-333333333333",
  role: "admin",
  username: null,
  email: "a@example.test",
  displayName: "Admin",
};

describe("routes", () => {
  it("should redirect signed-out users to login", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => apiError(401, "UNAUTHENTICATED"),
      "POST /api/v1/auth/refresh": () => apiError(401, "REFRESH_MISSING"),
    });
    const { router } = renderApp("/admin");

    expect(
      await screen.findByRole("heading", { name: "Sign in to GCSE Coach" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("should send a student away from the admin page to their own home", async () => {
    installFakeApi({ "GET /api/v1/users/me": () => json(STUDENT) });
    const { router } = renderApp("/admin");

    await screen.findByRole("heading", { name: "Hi Sam!" });
    expect(router.state.location.pathname).toBe("/");
  });

  it("should show the admin page to admins", async () => {
    installFakeApi({ "GET /api/v1/users/me": () => json(ADMIN) });
    renderApp("/admin");

    expect(await screen.findByRole("heading", { name: "Admin" })).toBeInTheDocument();
  });

  it("should show an error when the session can't be loaded", async () => {
    installFakeApi({ "GET /api/v1/users/me": () => apiError(500, "INTERNAL_ERROR") });
    renderApp("/");

    expect(await screen.findByText(/Something went wrong/)).toHaveAttribute("role", "status");
  });

  it("should show not found for unknown paths", async () => {
    installFakeApi({});
    renderApp("/nope");

    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it.each([
    ["succeeds", () => new Response(null, { status: 204 })],
    ["fails", () => apiError(500, "INTERNAL_ERROR")],
  ])("should sign out and return to login when logout %s", async (_label, logoutResponse) => {
    const fetchMock = installFakeApi({
      "GET /api/v1/users/me": [() => json(STUDENT), () => apiError(401, "UNAUTHENTICATED")],
      "POST /api/v1/auth/logout": logoutResponse,
      "POST /api/v1/auth/refresh": () => apiError(401, "REFRESH_MISSING"),
    });
    const { router } = renderApp("/");

    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await screen.findByRole("heading", { name: "Sign in to GCSE Coach" });
    expect(router.state.location.pathname).toBe("/login");
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/auth/logout")).toBe(true);
  });
});
