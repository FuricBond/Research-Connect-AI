/**
 * P9 — useAddressSearch when a link brings the reader to a page with a query.
 *
 * The router renders the new page before it updates the address bar. Arriving from another page,
 * the bar still shows that page, so the router's query is used until it shows this one; after a
 * router change the page renders once more and reads the bar (a link to the same page with another
 * query is followed). A late router report for an address the bar has left is still ignored
 * (tests/calls-pages.test.tsx).
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let pathname = "/postings";
let reported = new URLSearchParams();
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => reported,
}));

import { useAddressSearch } from "../hooks/useAddressSearch";

beforeEach(() => {
  window.history.replaceState(null, "", "/dashboard");
  pathname = "/postings";
  reported = new URLSearchParams();
});

describe("useAddressSearch", () => {
  it("uses the router's query while the address bar still shows the page the reader came from", () => {
    reported = new URLSearchParams("view=mine&status=OPEN");
    const { result } = renderHook(() => useAddressSearch());
    expect(result.current[0].get("view")).toBe("mine");
    expect(result.current[0].get("status")).toBe("OPEN");
  });

  it("follows a link to the same page with another query once the bar shows it", () => {
    window.history.replaceState(null, "", "/postings");
    const { result, rerender } = renderHook(() => useAddressSearch());
    expect(result.current[0].get("view")).toBeNull();

    // The router reports the link first; the bar is updated when the navigation commits.
    reported = new URLSearchParams("view=mine");
    act(() => {
      window.history.pushState(null, "", "/postings?view=mine");
      rerender();
    });
    expect(result.current[0].get("view")).toBe("mine");
  });

  it("keeps go() in charge on its own page", () => {
    window.history.replaceState(null, "", "/postings?view=mine");
    reported = new URLSearchParams("view=mine");
    const { result } = renderHook(() => useAddressSearch());
    act(() => result.current[1]("/postings?view=mine&status=DRAFT"));
    // The router has not reported it yet; the bar is the truth.
    expect(result.current[0].get("status")).toBe("DRAFT");
  });
});
