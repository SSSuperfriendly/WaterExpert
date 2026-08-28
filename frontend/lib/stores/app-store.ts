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
  };
});

export { LoginResponse };
