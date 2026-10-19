"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * P5 — a page whose state lives in its query string (calls for papers: `/browse?type=…&page=2`).
 *
 * The address bar is the truth: the value returned is what `window.location` shows, so a router
 * notification that trails it (the router applies history updates in a transition) can never put
 * an older state back. `useSearchParams` is read only so that links, back and forward re-render
 * the page. `go(href)` records a new state with the browser's own history — no page navigation
 * is ever pending behind the person's back (the P2 search fix) — and an unchanged address adds
 * no history entry. Must be used inside a Suspense boundary.
 *
 * P9: a link renders the new page before the router updates the address bar. Arriving from
 * another page, the bar still shows that page, so until it shows this one the router's query is
 * used (the bar cannot be on another page otherwise). And after every router change the page
 * renders once more, once the bar is up to date, so a link to this page with another query
 * (Discover → My postings) is followed rather than left behind.
 */
export function useAddressSearch(): [URLSearchParams, (href: string, options?: { replace?: boolean }) => void] {
  const reported = useSearchParams();
  const pathname = usePathname();
  const [, rerender] = useState(0);
  const reportedText = reported?.toString() ?? "";

  useEffect(() => {
    rerender((n) => n + 1);
  }, [reportedText, pathname]);

  const go = useCallback((href: string, options: { replace?: boolean } = {}) => {
    const next = new URL(href, window.location.href);
    if (next.pathname === window.location.pathname && next.search === window.location.search) return;
    if (options.replace) window.history.replaceState(null, "", `${next.pathname}${next.search}`);
    else window.history.pushState(null, "", `${next.pathname}${next.search}`);
    rerender((n) => n + 1);
  }, []);

  const arriving = typeof window !== "undefined" && pathname !== null && window.location.pathname !== pathname;
  const current = typeof window === "undefined" || arriving ? new URLSearchParams(reportedText) : new URLSearchParams(window.location.search);
  return [current, go];
}
