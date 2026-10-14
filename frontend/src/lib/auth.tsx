"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, clearSession, readSession, writeSession, type Session } from "./api";
import type { LoginResponse, Role } from "./types";

interface AuthState {
  session: Session | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<Session>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSession(readSession());
    setReady(true);
    const onExpired = () => setSession(null);
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await api<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    const next = { token: result.token, user: result.user };
    writeSession(next);
    setSession(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const value = useMemo(() => ({ session, ready, login, logout }), [session, ready, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

/** Which roles see each section. This only shapes the UI; the backend enforces access. */
export const SECTION_ROLES = {
  overview: ["analyst", "agent", "supervisor"],
  queue: ["agent", "supervisor"],
  customers: ["analyst", "agent", "supervisor"],
  ask: ["analyst", "supervisor"],
  briefs: ["agent", "supervisor"],
  reviews: ["agent", "supervisor"],
  quality: ["analyst", "supervisor"],
} as const satisfies Record<string, readonly Role[]>;

export type Section = keyof typeof SECTION_ROLES;

export function canSee(role: Role | undefined, section: Section) {
  return !!role && (SECTION_ROLES[section] as readonly Role[]).includes(role);
}
