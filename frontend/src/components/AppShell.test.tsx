// frontend/src/components/AppShell.test.tsx
/**
 * Covers:
 * - students get the bottom tab bar, with the current tab marked
 * - guardians and admins get no tab bar; the logo goes to their home
 * - the account menu opens, shows who's signed in, and closes on Escape
 *   and on a click outside; students see sounds and subjects, others don't
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { GUARDIAN, installFakeApi, json, STUDENT } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

describe("AppShell", () => {
  it("should show students a tab bar with the current tab marked", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(STUDENT),
      "GET /api/v1/me/badges": () => json([]),
    });
    renderApp("/badges");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Badges" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  it("should give guardians no tab bar and a logo that goes to their page", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(GUARDIAN),
      "GET /api/v1/guardian/students": () => json([]),
    });
    renderApp("/guardian");

    expect(await screen.findByRole("link", { name: "GCSE Coach" })).toHaveAttribute(
      "href",
      "/guardian",
    );
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("should open the account menu, then close it on Escape and on an outside click", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(GUARDIAN),
      "GET /api/v1/guardian/students": () => json([]),
    });
    renderApp("/guardian");
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Account menu" });

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Signed in as")).toHaveTextContent(GUARDIAN.displayName);
    expect(screen.queryByRole("checkbox", { name: "Sounds" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy notice" })).toHaveAttribute(
      "href",
      "/privacy",
    );

    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    await user.click(screen.getByRole("heading", { level: 1 }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("should offer students sounds and changing subjects in the menu", async () => {
    installFakeApi({
      "GET /api/v1/users/me": () => json(STUDENT),
      "GET /api/v1/me/badges": () => json([]),
    });
    renderApp("/badges");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Account menu" }));

    expect(screen.getByRole("checkbox", { name: "Sounds" })).not.toBeChecked();
    expect(screen.getByRole("link", { name: "Change my subjects" })).toHaveAttribute(
      "href",
      "/setup",
    );
  });
});
