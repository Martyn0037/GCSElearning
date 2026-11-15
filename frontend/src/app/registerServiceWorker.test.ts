// frontend/src/app/registerServiceWorker.test.ts
/**
 * Covers: no registration in development, without service-worker support, or
 * on localhost; registers /sw.js on load in production on a real domain; a
 * failed registration is ignored.
 */
import { describe, expect, it, vi } from "vitest";

import { registerServiceWorker } from "./registerServiceWorker";

describe("registerServiceWorker", () => {
  it("should not register in development", () => {
    const register = vi.fn();
    const nav = { serviceWorker: { register } } as unknown as Navigator;
    expect(registerServiceWorker(false, nav, "coach.example.com")).toBe(false);
  });

  it("should not register on localhost", () => {
    const register = vi.fn();
    const nav = { serviceWorker: { register } } as unknown as Navigator;
    expect(registerServiceWorker(true, nav, "localhost")).toBe(false);
    expect(register).not.toHaveBeenCalled();
  });

  it("should not register without service-worker support", () => {
    expect(registerServiceWorker(true, {} as Navigator, "coach.example.com")).toBe(false);
  });

  it("should register /sw.js once the page has loaded, ignoring failures", async () => {
    // Arrange
    const register = vi.fn(() => Promise.reject(new Error("blocked")));
    const nav = { serviceWorker: { register } } as unknown as Navigator;

    // Act
    const attempted = registerServiceWorker(true, nav, "coach.example.com");
    window.dispatchEvent(new Event("load"));
    await Promise.resolve();

    // Assert
    expect(attempted).toBe(true);
    expect(register).toHaveBeenCalledWith("/sw.js");
  });
});
