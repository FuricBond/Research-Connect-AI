"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";

/**
 * P5 — a page whose state lives in its query string (calls for papers: `/browse?type=…&page=2`).
 *
 * The address bar is the truth: the value returned is what `window.location` shows, so a router
 * notification that trails it (the router applies history updates in a transition) can never put
 * an older state back. `useSearchParams` is read only so that links, back and forward re-render
 * the page. `go(href)` records a new state with the browser's own history — no page navigation
 * is ever pending behind the person's back (the P2 search fix) — and an unchanged address adds
 * no history entry. Must be used inside a Suspense boundary.
 */
export function useAddressSearch(): [URLSearchParams, (href: string, options?: { replace?: boolean }) => void] {
  const reported = useSearchParams();
  const [, rerender] = useState(0);

  const go = useCallback((href: string, options: { replace?: boolean } = {}) => {
    const next = new URL(href, window.location.href);
    if (next.pathname === window.location.pathname && next.search === window.location.search) return;
    if (options.replace) window.history.replaceState(null, "", `${next.pathname}${next.search}`);
    else window.history.pushState(null, "", `${next.pathname}${next.search}`);
    rerender((n) => n + 1);
  }, []);

  const current = typeof window === "undefined" ? new URLSearchParams(reported.toString()) : new URLSearchParams(window.location.search);
  return [current, go];
}
