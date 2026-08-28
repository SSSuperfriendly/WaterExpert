"use client";

// Client-side persistence of the authenticated session. The JWT is kept in
// sessionStorage (survives refresh, cleared on tab close) next to the profile,
// mirroring how the static frontend already gated access.

const AUTH_STORAGE_KEY = "waterexpert.auth.profile";

export interface StoredAuth {
  username: string;
  display_name: string;
  role: string;
  access_token?: string;
}

export function readStoredAuth(): StoredAuth | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredAuth>;
    if (parsed && parsed.username) {
      return {
        username: String(parsed.username),
        display_name: String(parsed.display_name ?? parsed.username),
        role: String(parsed.role ?? "reviewer"),
        access_token:
          typeof parsed.access_token === "string" ? parsed.access_token : undefined,
      };
    }
  } catch {
    // ignore storage / parse errors
  }
  return null;
}

export function writeStoredAuth(auth: StoredAuth): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  } catch {
    // ignore storage errors
  }
}

export function clearStoredAuth(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
}

export function getStoredToken(): string | null {
  return readStoredAuth()?.access_token ?? null;
}
