"use client";

import { useEffect, useRef } from "react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { getKnownPaper, getPaperOrigin, getSelectedWork, isPaperId, setSelectedWork } from "../../hooks/useSelectedWork";
import type { ResearchWorkRead } from "../../types/discovery";

/**
 * P5 — the paper a paper-based page (similar papers, find venues) works from.
 *
 * The address names it (`?paper=<id>`), so reload, back and forward keep their own paper; with no
 * paper in the address, the last paper chosen in this tab is used, as before P5, and written into
 * the address. Its details come from this tab's memory (there is no "paper by id" endpoint); a
 * shared link to a paper this tab never saw still works from the id, without the details.
 * An id that cannot be a paper id is ignored rather than sent to the API.
 */
export function usePaperContext(hrefFor: (workId: string) => string) {
  const [params, go] = useAddressSearch();
  const raw = params.get("paper");
  const urlId = isPaperId(raw) ? raw : null;
  const selected = getSelectedWork();
  const selectedId = selected?.id ?? null;
  const paperId = urlId ?? selectedId;
  const work: ResearchWorkRead | null = urlId ? getKnownPaper(urlId) : selected;

  // Arrived without a paper in the address: record the one being shown, without a history entry.
  useEffect(() => {
    if (!urlId && isPaperId(selectedId)) go(hrefFor(selectedId), { replace: true });
  }, [urlId, selectedId, go, hrefFor]);

  // Focus goes to the paper's title after the paper changes on this page (a choice, back or
  // forward), never on arrival: the control that made the choice is gone.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previous = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (previous.current !== undefined && previous.current !== paperId && paperId) headingRef.current?.focus();
    previous.current = paperId;
  }, [paperId]);

  const choose = (next: ResearchWorkRead) => {
    setSelectedWork(next);
    go(hrefFor(next.id));
  };

  return { paperId, work, origin: getPaperOrigin() ?? "/", headingRef, choose };
}
