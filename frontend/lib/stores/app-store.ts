"use client";

import { create } from "zustand";
import type { LoginResponse } from "@/lib/api/contracts";

const SESSION_STORAGE_KEY = "waterexpert.auth.profile";

export interface AuthProfile {
  username: string;
  display_name: string;
  role: string;
}

interface AppState {
  // Auth
  session: AuthProfile | null;
  authReady: boolean;
  setSession: (session: AuthProfile | null) => void;
  clearSession: () => void;

  // Station context (default "2586").
  stationCode: string;
  setStationCode: (code: string) => void;

  // Active prediction job (kept in memory only).
  activeJobId: string | null;
  setActiveJobId: (jobId: string | null) => void;
}

function readSession(): AuthProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthProfile>;
    if (parsed && parsed.username) {
      return {
        username: String(parsed.username),
        display_name: String(parsed.display_name ?? parsed.username),
        role: String(parsed.role ?? "reviewer"),
      };
    }
  } catch {
    // ignore parse errors
  }
  return null;
}

export const useAppStore = create<AppState>((set) => ({
  session: readSession(),
  authReady: true,
  setSession: (session) => {
    if (typeof window !== "undefined") {
      try {
        if (session) {
          window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
        } else {
          window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
        }
      } catch {
        // ignore storage errors
      }
    }
    set({ session });
  },
  clearSession: () => {
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      } catch {
        // ignore storage errors
      }
    }
    set({ session: null });
  },

  stationCode: "2586",
  setStationCode: (stationCode) => set({ stationCode }),

  activeJobId: null,
  setActiveJobId: (activeJobId) => set({ activeJobId }),
}));

export { LoginResponse };
