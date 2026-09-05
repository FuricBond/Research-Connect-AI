"use client";

/**
 * useSelectedWork — ephemeral session hook for transferring the selected
 * ResearchWorkRead between Next.js pages (/similar and /opportunities).
 *
 * Uses sessionStorage so state is cleared when the browser tab closes.
 * No server-side state, no personalization, no persistence across sessions.
 */

import type { ResearchWorkRead } from "../types/discovery";

const SESSION_KEY = "rc_selected_work";

export function setSelectedWork(work: ResearchWorkRead): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(work));
  } catch {
    // sessionStorage may be unavailable in private browsing contexts
  }
}

export function getSelectedWork(): ResearchWorkRead | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ResearchWorkRead;
  } catch {
    return null;
  }
}

export function clearSelectedWork(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}
