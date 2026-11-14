// frontend/src/app/queryClient.test.ts
/**
 * Covers: no retries for 4xx; up to 2 retries for 5xx/network; client defaults.
 */
import { describe, expect, it } from "vitest";

import { ApiError } from "../api/http";
import { createQueryClient, shouldRetry } from "./queryClient";

describe("shouldRetry", () => {
  it("should not retry client errors", () => {
    expect(shouldRetry(0, new ApiError(404, "RESOURCE_NOT_FOUND", "x"))).toBe(false);
  });

  it("should retry server and network errors twice", () => {
    const error = new ApiError(0, "NETWORK_ERROR", "x");
    expect([0, 1, 2].map((n) => shouldRetry(n, error))).toEqual([true, true, false]);
  });

  it("should never retry mutations by default", () => {
    expect(createQueryClient().getDefaultOptions().mutations?.retry).toBe(false);
  });
});
