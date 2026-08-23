// frontend/src/api/client.ts
//
// The one place a request leaves the browser.
//
// Phase 4 made every route require a key, which broke the bundled HTML UI
// because it had no way to send one. This is the fix, and it is centralised on
// purpose: a fetch call written anywhere else would forget the header, get a
// 401, and the next person would "fix" it by loosening the server.
//
// The key is held in sessionStorage, not localStorage. sessionStorage dies with
// the tab, so a shared or unattended machine does not keep an admin credential
// for this system sitting in browser storage indefinitely. It costs the user
// one paste per session and removes a whole class of "I forgot I was logged in"
// problem.

import { demoResolve } from "./demoApi";

const API_ROOT = "/api/v1";
const STORAGE_KEY = "qqd.apiKey";

/**
 * True when the app is running as a static demo (GitHub Pages or explicit env).
 * In demo mode, all API calls are resolved by the in-browser mock.
 */
export function isDemo(): boolean {
  // Build-time flag set by CI
  if (import.meta.env.VITE_DEMO_MODE === "true") return true;
  // Runtime detection: running on github.io
  if (typeof window !== "undefined" && window.location.hostname.endsWith("github.io")) return true;
  return false;
}

export class ApiError extends Error {
  readonly status: number;
  readonly correlationId?: string;

  constructor(status: number, title: string, correlationId?: string) {
    super(title);
    this.name = "ApiError";
    this.status = status;
    this.correlationId = correlationId;
  }

  /** Whether the caller should be asked for a key rather than shown an error. */
  get needsKey(): boolean {
    return this.status === 401;
  }
}

/** RFC 9457 problem document, as returned by src/api/errors.py. */
interface ProblemDocument {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  correlation_id?: string;
}

export function getApiKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing modes can throw on storage access. Degrading to "no key
    // stored" is correct: the user is prompted, which is annoying but works.
    return null;
  }
}

export function setApiKey(key: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, key.trim());
  } catch {
    /* see getApiKey */
  }
}

export function clearApiKey(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* see getApiKey */
  }
}

/**
 * Fired when the server rejects the stored key.
 *
 * Without this, a wrong or expired key leaves every panel sitting on its
 * loading state or showing "authentication required" with no way to act on it,
 * and the user's only recourse is to know to clear their own session storage.
 * The gate listens for this and re-prompts.
 */
export const AUTH_FAILED_EVENT = "qqd:auth-failed";

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Demo mode: resolve from in-browser mock, no network call.
  if (isDemo()) {
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    return demoResolve(method, path, body) as T;
  }

  const key = getApiKey();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (key) headers.set("Authorization", `Bearer ${key}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers });

  if (response.status === 401) {
    // The stored key is wrong or gone. Drop it and tell the gate, so the user
    // is asked again rather than left staring at a panel that never loads.
    clearApiKey();
    window.dispatchEvent(new Event(AUTH_FAILED_EVENT));
  }

  if (!response.ok) {
    // Never surface a raw provider or server error (CONTEXT.md rule 4). The
    // server already returns a safe title and a correlation ID; anything we
    // cannot parse becomes a generic message rather than raw response text,
    // which could contain a stack trace with employee names in it.
    let problem: ProblemDocument = {};
    try {
      problem = (await response.json()) as ProblemDocument;
    } catch {
      /* non-JSON error body -- deliberately discarded */
    }
    throw new ApiError(
      response.status,
      problem.title ?? "The request could not be completed.",
      problem.correlation_id,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
};
