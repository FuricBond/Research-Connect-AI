"use client";

/**
 * useSelectedWork — ephemeral session hook for transferring the selected
 * ResearchWorkRead between Next.js pages (/similar and /opportunities).
 *
 * Uses sessionStorage so state is cleared when the browser tab closes.
 * No server-side state, no personalization, no persistence across sessions.
 *
 * P5: the paper's id also travels in the address (`/similar?paper=<id>`), so a reload, back and
 * forward each keep their own paper. The API has no "paper by id" endpoint (plan Q4), so the
 * paper's details come from here: every paper chosen in this tab is remembered by id (the last
 * few), with the search it was chosen from (the breadcrumb's way back).
 */

import type { ResearchWorkRead } from "../types/discovery";
import { isUuid } from "../utils/ids";

const SESSION_KEY = "rc_selected_work";
const KNOWN_KEY = "rc_known_papers";
const ORIGIN_KEY = "rc_paper_origin";
/** How many chosen papers a tab remembers. */
const KNOWN_LIMIT = 30;

/** Whether `value` can be a paper id (the API answers 422 to anything else; it is not asked). */
export function isPaperId(value: string | null | undefined): value is string {
  return isUuid(value);
}

function readKnown(): ResearchWorkRead[] {
  try {
    const raw = window.sessionStorage.getItem(KNOWN_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? (parsed as ResearchWorkRead[]) : [];
  } catch {
    return [];
  }
}

export function setSelectedWork(work: ResearchWorkRead, origin?: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(work));
    const known = [work, ...readKnown().filter((paper) => paper.id !== work.id)].slice(0, KNOWN_LIMIT);
    window.sessionStorage.setItem(KNOWN_KEY, JSON.stringify(known));
    if (origin !== undefined) window.sessionStorage.setItem(ORIGIN_KEY, origin);
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

/** A paper chosen earlier in this tab, by id; null when this tab never saw it (a shared link). */
export function getKnownPaper(id: string): ResearchWorkRead | null {
  if (typeof window === "undefined") return null;
  const selected = getSelectedWork();
  if (selected?.id === id) return selected;
  return readKnown().find((paper) => paper.id === id) ?? null;
}

/** The search the selected paper was chosen from ("/?q=…"), if any. */
export function getPaperOrigin(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const origin = window.sessionStorage.getItem(ORIGIN_KEY);
    // Only a path on this site is ever used as a link.
    return origin && origin.startsWith("/") && !origin.startsWith("//") ? origin : null;
  } catch {
    return null;
  }
}

export function clearSelectedWork(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
    window.sessionStorage.removeItem(KNOWN_KEY);
    window.sessionStorage.removeItem(ORIGIN_KEY);
  } catch {
    // ignore
  }
}
