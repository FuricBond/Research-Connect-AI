"use client";

/**
 * Phase 6.2 — The single source of truth for who is signed in.
 *
 * Every part of the UI that needs the caller's identity or role reads it from here, so
 * the header, the route guards and the pages cannot disagree about whether somebody is
 * authenticated. localStorage remains the storage mechanism (see services/auth.ts); this
 * provider owns the in-memory state derived from it.
 *
 * The backend stays authoritative: a stored token is never assumed valid. On startup the
 * provider verifies it against `/auth/me` and clears it if the answer is no.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  AuthenticatedUser,
  LoginPayload,
  PlatformRole,
  RegisterPayload,
} from "../../types/auth";
import {
  getCurrentUser,
  login as loginRequest,
  register as registerRequest,
  setUnauthorizedHandler,
} from "../../services/api";
import {
  clearActiveIdentity,
  getStoredIdentity,
  isStoredSessionExpired,
  storeAuthenticatedUser,
  storeSession,
} from "../../services/auth";
import { clearSelectedWork } from "../../hooks/useSelectedWork";

/**
 * `loading` lasts until the stored credentials have been checked. Route guards must not
 * render protected content during it, otherwise a page flashes before we know who is there.
 */
export type SessionStatus = "loading" | "unauthenticated" | "authenticated";

export interface SessionContextValue {
  status: SessionStatus;
  user: AuthenticatedUser | null;
  /** The signed-in account's researcher profile, or null when it has none. */
  profileId: string | null;
  role: PlatformRole | null;
  /** UX convenience only — the backend remains the authorization boundary. */
  hasRole: (...roles: PlatformRole[]) => boolean;
  login: (payload: LoginPayload) => Promise<AuthenticatedUser>;
  register: (payload: RegisterPayload) => Promise<AuthenticatedUser>;
  logout: () => void;
  /** Re-reads the account from the backend, e.g. after an administrator changes a role. */
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  // While a sign-in is in flight its own 401 must not be mistaken for a lost session.
  const authenticatingRef = useRef(false);

  const applyUser = useCallback((nextUser: AuthenticatedUser) => {
    storeAuthenticatedUser(nextUser);
    setUser(nextUser);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    clearActiveIdentity();
    // Anything derived from the previous account goes too, so the next person to use
    // this browser does not inherit the last one's working state.
    clearSelectedWork();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  // ── Session restoration ───────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      const identity = getStoredIdentity();

      // Nothing stored at all: no request to make.
      if (!identity.token && !identity.userId && !identity.profileId) {
        if (!cancelled) setStatus("unauthenticated");
        return;
      }

      // A token whose recorded expiry has already passed cannot succeed; drop it without
      // a round trip. Anything else is verified by the backend rather than trusted here.
      if (isStoredSessionExpired()) {
        if (!cancelled) clearSession();
        return;
      }

      try {
        // With no token but a stored user id this still resolves when the backend runs
        // with AUTH_DEV_IDENTITY_ENABLED=true, preserving the existing developer
        // fallback. In production it answers 401 and the session is cleared.
        const verified = await getCurrentUser();
        if (!cancelled) applyUser(verified);
      } catch {
        if (!cancelled) clearSession();
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, [applyUser, clearSession]);

  // ── Centralised 401 handling ──────────────────────────────────────────────
  //
  // The API client reports; this decides. Clearing the state is all that happens here:
  // the route guard sends the person to sign in if they are on a protected page, which
  // keeps public pages from redirecting and makes a redirect loop impossible.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (authenticatingRef.current) return;
      clearSession();
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  const login = useCallback(
    async (payload: LoginPayload) => {
      authenticatingRef.current = true;
      try {
        const response = await loginRequest(payload);
        storeSession(response);
        applyUser(response.user);
        return response.user;
      } finally {
        authenticatingRef.current = false;
      }
    },
    [applyUser]
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      authenticatingRef.current = true;
      try {
        // Registration returns a token, so a new account is signed in immediately.
        const response = await registerRequest(payload);
        storeSession(response);
        applyUser(response.user);
        return response.user;
      } finally {
        authenticatingRef.current = false;
      }
    },
    [applyUser]
  );

  // Safe to call when already signed out: clearing an empty session is a no-op.
  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  const refresh = useCallback(async () => {
    try {
      applyUser(await getCurrentUser());
    } catch {
      clearSession();
    }
  }, [applyUser, clearSession]);

  const value = useMemo<SessionContextValue>(
    () => ({
      status,
      user,
      profileId: user?.profile_id ?? null,
      role: user?.role ?? null,
      hasRole: (...roles: PlatformRole[]) => user !== null && roles.includes(user.role),
      login,
      register,
      logout,
      refresh,
    }),
    [status, user, login, register, logout, refresh]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used inside a SessionProvider.");
  }
  return context;
}
