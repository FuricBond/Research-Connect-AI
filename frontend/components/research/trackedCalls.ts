"use client";

import { useMemo } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchWorkspaceItems } from "../../services/api";
import type { WorkspaceItem } from "../../types/workspace";

/** The workspace list allows 100 items per request; more tracked calls than that are not looked up. */
const LOOKUP_LIMIT = 100;

/**
 * P5 — which calls the signed-in account already tracks, so a list or a call's page can say
 * "Saved" and show the workspace status. One request, shared by everything on the page that
 * asks (the browse list and its cards; a call's page). A visitor asks nothing ("idle").
 * The most recently updated 100 tracked calls (archived included) are looked up; saving is
 * idempotent on the server, so a call beyond them that reads "Save" is saved without harm and
 * then shows its status.
 */
export function useTrackedCalls() {
  const resource = useApiResource("workspace:tracked-calls", (signal) =>
    fetchWorkspaceItems({ include_archived: true, limit: LOOKUP_LIMIT }, undefined, signal)
  );
  const byCall = useMemo(() => {
    const map = new Map<string, WorkspaceItem>();
    for (const item of resource.data?.items ?? []) map.set(item.opportunity_id, item);
    return map;
  }, [resource.data]);
  return { status: resource.status, byCall };
}
