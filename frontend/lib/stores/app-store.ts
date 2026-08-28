"use client";

import { create } from "zustand";
import type { LoginResponse } from "@/lib/api/contracts";
import {
  clearStoredAuth,
  readStoredAuth,
  writeStoredAuth,
  type StoredAuth,
} from "@/lib/auth-token";

export interface AuthProfile {
  username: string;
  display_name: string;
  role: string;
}

export type AuthCredentials = AuthProfile & { access_token?: string };

interface AppState {
  // Auth
  session: AuthProfile | null;
  authReady: boolean;
  setSession: (session: AuthCredentials | null) => void;
  clearSession: () => void;

  // Station context (default "2586").
  stationCode: string;
  setStationCode: (code: string) => void;

  // Active prediction job (kept in memory only).
  activeJobId: string | null;
  setActiveJobId: (jobId: string | null) => void;

  // Case context — the object every result page is attributed to. Persisted so
  // the evidence chain survives a refresh; results resolve against this case.
  activeCaseId: string | null;
  targetDate: string | null;
  setCaseContext: (caseId: string | null, targetDate?: string | null) => void;
  clearCaseContext: () => void;
}

const CASE_CONTEXT_KEY = "waterexpert.case.context";

function readCaseContext(): { caseId: string | null; targetDate: string | null } {
  if (typeof window === "undefined") return { caseId: null, targetDate: null };
  try {
    const raw = window.sessionStorage.getItem(CASE_CONTEXT_KEY);
    if (!raw) return { caseId: null, targetDate: null };
    const parsed = JSON.parse(raw) as { caseId?: string; targetDate?: string };
    return {
      caseId: typeof parsed.caseId === "string" ? parsed.caseId : null,
      targetDate: typeof parsed.targetDate === "string" ? parsed.targetDate : null,
    };
  } catch {
    return { caseId: null, targetDate: null };
  }
}

function toProfile(stored: StoredAuth): AuthProfile {
  return {
    username: stored.username,
    display_name: stored.display_name,
    role: stored.role,
  };
}

export const useAppStore = create<AppState>((set) => {
  const stored = readStoredAuth();
  const caseContext = readCaseContext();

  return {
    session: stored ? toProfile(stored) : null,
    authReady: true,
    setSession: (session) => {
      if (session) {
        writeStoredAuth(session);
      } else {
        clearStoredAuth();
      }
      set({
        session: session ? toProfile(session) : null,
      });
    },
    clearSession: () => {
      clearStoredAuth();
      set({ session: null });
    },

    stationCode: "2586",
    setStationCode: (stationCode) => set({ stationCode }),

    activeJobId: null,
    setActiveJobId: (activeJobId) => set({ activeJobId }),

    activeCaseId: caseContext.caseId,
    targetDate: caseContext.targetDate,
    setCaseContext: (activeCaseId, targetDate) => {
      if (typeof window !== "undefined") {
        try {
          window.sessionStorage.setItem(
            CASE_CONTEXT_KEY,
            JSON.stringify({ caseId: activeCaseId, targetDate: targetDate ?? null })
          );
        } catch {
          // ignore storage errors
        }
      }
      set({ activeCaseId, targetDate: targetDate ?? null });
    },
    clearCaseContext: () => {
      if (typeof window !== "undefined") {
        try {
          window.sessionStorage.removeItem(CASE_CONTEXT_KEY);
        } catch {
          // ignore storage errors
        }
      }
      set({ activeCaseId: null, targetDate: null });
    },
  };
});

export { LoginResponse };
