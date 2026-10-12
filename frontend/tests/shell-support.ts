/**
 * Shared set-up for the application-shell tests (P2): a signed-in (or signed-out) browser and a
 * fetch stand-in answering the requests the shell makes.
 */

import { vi } from "vitest";
import { clearActiveIdentity, storeSession } from "../services/auth";
import type { PlatformRole } from "../types/auth";
import { PROFILE_ID, jsonResponse, makeTokenResponse, makeUser } from "./factories";

/** jsdom has <dialog> but not showModal()/close(): give it the browser's behaviour. */
export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal?: () => void; close?: () => void };
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

export interface ShellRoutes {
  /** The unread count the API reports (0 by default). */
  unread?: () => number;
  /** Never answer /auth/me: the session stays "being restored". */
  pendingSession?: boolean;
  /** Other requests; return undefined to fall through to a 404. */
  other?: (url: string, init?: RequestInit) => Promise<Response> | undefined;
}

/** Stores a session for `role` (none for null) and installs a fetch mock; returns the mock. */
export function serveShell(role: PlatformRole | null, routes: ShellRoutes = {}) {
  if (role === null) clearActiveIdentity();
  else storeSession(makeTokenResponse({ user: makeUser({ role }) }));
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/auth/me")) {
      if (routes.pendingSession) return new Promise<Response>(() => {});
      return Promise.resolve(jsonResponse(makeUser({ role: role ?? "STUDENT" })));
    }
    if (url.endsWith("/api/v1/notifications/unread-count")) {
      return Promise.resolve(jsonResponse({ profile_id: PROFILE_ID, unread_count: routes.unread ? routes.unread() : 0 }));
    }
    const other = routes.other?.(url, init);
    if (other) return other;
    return Promise.resolve(jsonResponse({ detail: `unexpected request ${url}` }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** How many requests went to a path ending in `part`. */
export function requestsTo(fetchMock: ReturnType<typeof serveShell>, part: string): number {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(part)).length;
}
