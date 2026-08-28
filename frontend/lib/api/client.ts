"use client";

import { clearStoredAuth, getStoredToken } from "@/lib/auth-token";

// Default to same-origin (empty base) so the statically exported frontend calls
// the backend that serves it — FastAPI mounts the app at `/ui` and the API at
// `/api/v1/...` on the same host, so a relative URL works for any deployment
// target, not just localhost. During `next dev` (frontend on :3000, backend on
// :8000) set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 so requests reach
// the backend.
export function apiBaseUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  return (fromEnv || "").replace(/\/+$/, "");
}

const AUTH_PATH_PREFIX = "/api/v1/auth/";

/** Paths that never carry (or need) a bearer token. */
function isAuthPath(path: string): boolean {
  return path.startsWith(AUTH_PATH_PREFIX);
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type QueryParams = Record<string, string | number | boolean | undefined | null>;

function buildQuery(params?: QueryParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    let detail = "";
    if (body && typeof body === "object" && "detail" in body) {
      detail = String((body as { detail: unknown }).detail);
    } else if (typeof body === "string") {
      detail = body;
    }
    throw new ApiError(response.status, detail);
  }

  return body as T;
}

async function request<T>(
  method: string,
  path: string,
  options: {
    query?: QueryParams;
    body?: unknown;
    formData?: FormData;
    headers?: Record<string, string>;
  } = {}
): Promise<T> {
  const url = `${apiBaseUrl()}${path}${buildQuery(options.query)}`;

  const headers: Record<string, string> = { ...options.headers };

  if (!isAuthPath(path)) {
    const token = getStoredToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
    // Do not set Content-Type manually; the browser adds the multipart boundary.
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, { method, headers, body });
  } catch {
    throw new ApiError(0, "Network error");
  }

  if (response.status === 401 && !isAuthPath(path)) {
    // Token missing/expired on a protected endpoint: clear the session and
    // bounce to the login page (full reload rebuilds the client auth gate).
    clearStoredAuth();
    if (typeof window !== "undefined" && !window.location.pathname.endsWith("/login")) {
      window.location.assign("/ui/login/");
    }
  }

  return parseResponse<T>(response);
}

export const apiClient = {
  get: <T>(path: string, query?: QueryParams) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: QueryParams) =>
    request<T>("POST", path, { body, query }),
  upload: <T>(path: string, formData: FormData, query?: QueryParams) =>
    request<T>("POST", path, { formData, query }),
};

/** Resolve a backend-relative asset URL (e.g. download_url / media paths). */
export function absoluteAssetUrl(path: string): string {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${apiBaseUrl()}${path.startsWith("/") ? "" : "/"}${path}`;
}
