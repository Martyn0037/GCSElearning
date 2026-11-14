// frontend/src/api/http.ts
/**
 * The single HTTP client used by all generated API hooks.
 *
 * Responsibilities:
 * - same-origin requests with cookies (auth tokens are httpOnly cookies)
 * - echo the CSRF cookie in `X-CSRF-Token` on state-changing requests
 * - on an expired session, refresh once (shared across concurrent calls) and retry
 * - turn error bodies into a typed `ApiError` carrying the server's traceId
 * - time out requests that hang
 * - validate every response body against its generated Zod schema
 */
import { z } from "zod";

export const CSRF_COOKIE = "gc_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
export const REQUEST_TIMEOUT_MS = 15_000;
const REFRESH_PATH = "/api/v1/auth/refresh";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
/** 401 codes that mean "the access token is stale; a refresh may fix it". */
const REFRESHABLE_CODES = new Set(["UNAUTHENTICATED", "TOKEN_EXPIRED", "TOKEN_INVALID"]);

const errorBodySchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    traceId: z.string().nullable(),
  }),
});

/** An error response from the API, or a network/timeout failure (status 0). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly traceId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Read a cookie visible to JavaScript (only the CSRF cookie is). */
export function readCookie(name: string, cookieString: string = document.cookie): string | null {
  for (const part of cookieString.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

async function toApiError(response: Response): Promise<ApiError> {
  const parsed = errorBodySchema.safeParse(await response.json().catch(() => null));
  if (parsed.success) {
    const { code, message, traceId } = parsed.data.error;
    return new ApiError(response.status, code, message, traceId);
  }
  return new ApiError(response.status, "HTTP_ERROR", `Request failed (${response.status})`);
}

async function send(url: string, init: RequestInit): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);
  }
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  try {
    return await fetch(url, { ...init, method, headers, signal, credentials: "same-origin" });
  } catch (error) {
    if (init.signal?.aborted) throw error; // the caller cancelled; let it propagate
    const timedOut = timeout.aborted;
    throw new ApiError(
      0,
      timedOut ? "TIMEOUT" : "NETWORK_ERROR",
      timedOut
        ? "The server took too long to respond."
        : "Can't reach the server. Check your connection.",
    );
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/**
 * Refresh the session once, however many requests discover expiry at the same time.
 * Resolves `true` when retrying the original request is worthwhile.
 */
export function refreshSession(): Promise<boolean> {
  // No CSRF cookie means no session was ever issued (or it was cleared):
  // there is nothing to refresh, so don't send a request that must fail.
  if (!readCookie(CSRF_COOKIE)) return Promise.resolve(false);
  refreshInFlight ??= (async () => {
    try {
      const response = await send(REFRESH_PATH, { method: "POST" });
      if (response.ok) return true;
      // Another tab refreshed a moment ago; its new cookies are already set.
      const error = await toApiError(response);
      return error.code === "REFRESH_RACE";
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Request options: standard fetch options plus the response schema Orval passes in. */
export type ApiRequestInit = RequestInit & { schema?: z.ZodType };

/**
 * Orval mutator: performs the request and returns the validated JSON body.
 *
 * @throws ApiError on any non-2xx response, network failure, timeout, or a
 *   response that doesn't match its schema (`INVALID_RESPONSE`).
 */
export async function apiFetch<T>(url: string, options: ApiRequestInit = {}): Promise<T> {
  const { schema, ...init } = options;
  let response = await send(url, init);

  if (response.status === 401 && url !== REFRESH_PATH && !url.startsWith("/api/v1/auth/")) {
    const error = await toApiError(response.clone());
    if (REFRESHABLE_CODES.has(error.code) && (await refreshSession())) {
      response = await send(url, init);
    }
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json();
  if (!schema) return body as T;
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      response.status,
      "INVALID_RESPONSE",
      "The server sent something unexpected. Please try again.",
      response.headers.get("x-trace-id"),
    );
  }
  return parsed.data as T;
}

export default apiFetch;

/** Tells Orval that generated hooks reject with `ApiError` (the parameter is unused by design). */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export type ErrorType<_E> = ApiError;
/** Request bodies are sent as-is. */
export type BodyType<B> = B;
