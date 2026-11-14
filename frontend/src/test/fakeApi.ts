// frontend/src/test/fakeApi.ts
// A tiny in-memory stand-in for the backend, installed as global `fetch`.
import { vi } from "vitest";

import type { UserOut } from "../api/generated/model";

export type Handler = (init: RequestInit) => Response | Promise<Response>;

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function apiError(status: number, code: string, message = code): Response {
  return json({ error: { code, message, traceId: "trace-1" } }, status);
}

export const STUDENT: UserOut = {
  id: "11111111-1111-4111-8111-111111111111",
  role: "student",
  displayName: "Sam",
  username: "sam10",
  email: null,
  setupCompleted: true,
};

export const GUARDIAN: UserOut = {
  id: "22222222-2222-4222-8222-222222222222",
  role: "guardian",
  displayName: "Alex",
  username: null,
  email: "alex@example.test",
  setupCompleted: false,
};

/**
 * Install a fake `fetch`. Keys are "METHOD /path". Each key may map to one
 * handler or a queue of handlers consumed in order (the last one repeats).
 *
 * @returns The mock, for asserting calls.
 */
export function installFakeApi(routes: Record<string, Handler | Handler[]>) {
  const queues = new Map(
    Object.entries(routes).map(([k, v]) => [k, Array.isArray(v) ? [...v] : [v]]),
  );
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const key = `${(init.method ?? "GET").toUpperCase()} ${url}`;
    const queue = queues.get(key);
    if (!queue || queue.length === 0) throw new Error(`Unexpected request: ${key}`);
    const handler = queue.length > 1 ? queue.shift() : queue[0];
    if (!handler) throw new Error(`No handler left for: ${key}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Headers of the n-th call to the fake fetch. */
export function headersOf(mock: ReturnType<typeof installFakeApi>, call: number): Headers {
  const init = mock.mock.calls[call]?.[1];
  return new Headers(init?.headers);
}

/** Parse the JSON body a request was sent with. */
export function jsonBody(init: RequestInit): unknown {
  if (typeof init.body !== "string") throw new Error("Expected a JSON string body");
  return JSON.parse(init.body);
}
