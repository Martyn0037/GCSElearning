// frontend/src/api/http.test.ts
/**
 * Covers:
 * - readCookie: present, absent, encoded values
 * - CSRF header added on POST, never on GET
 * - error bodies -> ApiError(code, message, traceId); non-JSON errors -> HTTP_ERROR
 * - 204 -> undefined; schema mismatch -> INVALID_RESPONSE; valid body returned
 * - expired session: one refresh then retry; concurrent 401s share one refresh
 * - no session cookie -> no refresh attempt
 * - REFRESH_RACE -> retry; failed refresh -> original 401 surfaces
 * - auth endpoints never trigger a refresh; non-refreshable 401 codes don't either
 * - network failure -> NETWORK_ERROR; timeout -> TIMEOUT; caller abort propagates
 */
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { apiError, headersOf, installFakeApi, json } from "../test/fakeApi";
import { ApiError, apiFetch, readCookie } from "./http";

const Thing = z.object({ id: z.number() });

describe("readCookie", () => {
  it("should return a decoded cookie value when present", () => {
    expect(readCookie("b", "a=1; b=x%20y; c=3")).toBe("x y");
  });

  it("should return null when the cookie is absent", () => {
    expect(readCookie("z", "a=1")).toBeNull();
  });
});

describe("apiFetch", () => {
  it("should send the CSRF cookie as a header on POST", async () => {
    document.cookie = "gc_csrf=tok123; path=/";
    const fetchMock = installFakeApi({ "POST /api/v1/x": () => json({ id: 1 }) });

    await apiFetch("/api/v1/x", { method: "POST" });

    expect(headersOf(fetchMock, 0).get("X-CSRF-Token")).toBe("tok123");
  });

  it("should not send a CSRF header on GET", async () => {
    document.cookie = "gc_csrf=tok123; path=/";
    const fetchMock = installFakeApi({ "GET /api/v1/x": () => json({ id: 1 }) });

    await apiFetch("/api/v1/x");

    expect(headersOf(fetchMock, 0).has("X-CSRF-Token")).toBe(false);
  });

  it("should return the body when it matches the schema", async () => {
    installFakeApi({ "GET /api/v1/x": () => json({ id: 7 }) });

    await expect(apiFetch("/api/v1/x", { schema: Thing })).resolves.toEqual({ id: 7 });
  });

  it("should reject a body that does not match the schema", async () => {
    installFakeApi({ "GET /api/v1/x": () => json({ id: "seven" }) });

    await expect(apiFetch("/api/v1/x", { schema: Thing })).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });

  it("should return undefined for 204 responses", async () => {
    installFakeApi({ "POST /api/v1/x": () => new Response(null, { status: 204 }) });

    await expect(apiFetch("/api/v1/x", { method: "POST" })).resolves.toBeUndefined();
  });

  it("should map the standard error body to ApiError", async () => {
    installFakeApi({ "GET /api/v1/x": () => apiError(404, "RESOURCE_NOT_FOUND", "Nope") });

    const error = await apiFetch("/api/v1/x").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "RESOURCE_NOT_FOUND",
      message: "Nope",
      traceId: "trace-1",
    });
  });

  it("should map a non-JSON error to HTTP_ERROR", async () => {
    installFakeApi({ "GET /api/v1/x": () => new Response("<html>", { status: 502 }) });

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ status: 502, code: "HTTP_ERROR" });
  });

  it("should not attempt a refresh when there is no session cookie", async () => {
    const fetchMock = installFakeApi({ "GET /api/v1/x": () => apiError(401, "UNAUTHENTICATED") });

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should refresh once and retry when the access token has expired", async () => {
    document.cookie = "gc_csrf=tok; path=/";
    const fetchMock = installFakeApi({
      "GET /api/v1/x": [() => apiError(401, "TOKEN_EXPIRED"), () => json({ id: 1 })],
      "POST /api/v1/auth/refresh": () => json({}),
    });

    await expect(apiFetch("/api/v1/x")).resolves.toEqual({ id: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("should share a single refresh between concurrent expired requests", async () => {
    document.cookie = "gc_csrf=tok; path=/";
    const fetchMock = installFakeApi({
      "GET /api/v1/a": [() => apiError(401, "TOKEN_EXPIRED"), () => json({ id: 1 })],
      "GET /api/v1/b": [() => apiError(401, "TOKEN_EXPIRED"), () => json({ id: 2 })],
      "POST /api/v1/auth/refresh": () => json({}),
    });

    await Promise.all([apiFetch("/api/v1/a"), apiFetch("/api/v1/b")]);

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/v1/auth/refresh");
    expect(refreshCalls).toHaveLength(1);
  });

  it("should retry after a refresh race because another tab already refreshed", async () => {
    document.cookie = "gc_csrf=tok; path=/";
    installFakeApi({
      "GET /api/v1/x": [() => apiError(401, "TOKEN_EXPIRED"), () => json({ id: 1 })],
      "POST /api/v1/auth/refresh": () => apiError(401, "REFRESH_RACE"),
    });

    await expect(apiFetch("/api/v1/x")).resolves.toEqual({ id: 1 });
  });

  it("should surface the original 401 when refresh fails", async () => {
    document.cookie = "gc_csrf=tok; path=/";
    installFakeApi({
      "GET /api/v1/x": () => apiError(401, "UNAUTHENTICATED"),
      "POST /api/v1/auth/refresh": () => apiError(401, "REFRESH_EXPIRED"),
    });

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHENTICATED",
    });
  });

  it("should not refresh for auth endpoints", async () => {
    const fetchMock = installFakeApi({
      "POST /api/v1/auth/login": () => apiError(401, "INVALID_CREDENTIALS"),
    });

    await expect(apiFetch("/api/v1/auth/login", { method: "POST" })).rejects.toMatchObject({
      code: "INVALID_CREDENTIALS",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should not refresh for a non-refreshable 401 code", async () => {
    const fetchMock = installFakeApi({ "GET /api/v1/x": () => apiError(401, "SOMETHING_ELSE") });

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("should report a network failure as NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("should report a timeout as TIMEOUT", async () => {
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(AbortSignal.abort());
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));

    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ code: "TIMEOUT" });
  });

  it("should propagate a caller's own abort unchanged", async () => {
    const abortError = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));

    await expect(apiFetch("/api/v1/x", { signal: AbortSignal.abort() })).rejects.toBe(abortError);
  });
});
