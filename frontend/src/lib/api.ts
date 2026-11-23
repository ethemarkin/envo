/**
 * Fetch wrapper for the Envo API.
 *
 * - Auth lives in HttpOnly cookies; the SPA never sees tokens.
 * - State-changing requests echo the `envo_csrf` cookie in `X-CSRF-Token`.
 * - A 401 triggers one refresh attempt (shared by concurrent requests),
 *   then the original request is retried once.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** The full JSON error body, e.g. `keys` or `errors` for validation failures. */
  readonly data: Record<string, unknown>;

  constructor(status: number, code: string, data: Record<string, unknown> = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

function buildInit(
  method: string,
  body: unknown,
  extraHeaders: Record<string, string> = {},
): RequestInit {
  const headers: Record<string, string> = { Accept: "application/json", ...extraHeaders };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie("envo_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  return {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

async function toError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
    if (typeof data?.detail === "string") code = data.detail;
    else if (Array.isArray(data?.detail)) code = "validation_error";
  } catch {
    // Non-JSON error body; keep the generic code.
  }
  return new ApiError(res.status, code, data);
}

let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  // The CSRF cookie lives as long as the refresh cookie; without it there is
  // no session to refresh.
  if (!readCookie("envo_csrf")) return Promise.resolve(false);
  refreshing ??= fetch("/api/auth/refresh", buildInit("POST", undefined))
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const NO_REFRESH = new Set(["/api/auth/login", "/api/auth/signup", "/api/auth/refresh"]);

async function send(
  method: string,
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
): Promise<Response> {
  let res = await fetch(path, buildInit(method, body, headers));
  if (res.status === 401 && !NO_REFRESH.has(path) && (await refreshSession())) {
    res = await fetch(path, buildInit(method, body, headers));
  }
  if (!res.ok) throw await toError(res);
  return res;
}

export async function api<T>(
  method: string,
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await send(method, path, body, headers);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch a text response (e.g. a .env export), its suggested filename and ETag. */
export async function getText(
  path: string,
): Promise<{ text: string; filename: string | null; etag: string | null }> {
  const res = await send("GET", path);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? null;
  return { text: await res.text(), filename, etag: res.headers.get("ETag") };
}

export const get = <T>(path: string) => api<T>("GET", path);
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, body);
export const patch = <T>(path: string, body: unknown) => api<T>("PATCH", path, body);
export const del = <T = void>(path: string) => api<T>("DELETE", path);
