"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { fetchWorkspaceItems, fetchWorkspaceSummary, removeWorkspaceItem, transitionWorkspaceStatus, updateWorkspaceItem } from "../../services/api";
import type { WorkspaceFilterParams, WorkspaceItem, WorkspaceItemUpdatePayload, WorkspaceStatus } from "../../types/workspace";
import { workspaceStatusMeta } from "../../utils/status";

export interface WorkspaceQuery {
  status: WorkspaceStatus | null;
  sort: "deadline" | "priority" | "updated";
  search: string;
}

/** A failed change, kept so the person can try it again. */
export interface FailedChange {
  itemId: string;
  title: string;
  target: WorkspaceStatus;
}

const SORT: Record<WorkspaceQuery["sort"], Pick<WorkspaceFilterParams, "sort_by" | "sort_order">> = {
  deadline: { sort_by: "deadline", sort_order: "asc" },
  priority: { sort_by: "priority", sort_order: "desc" },
  updated: { sort_by: "updated_at", sort_order: "desc" },
};

export function workspaceFilters(query: WorkspaceQuery): WorkspaceFilterParams {
  return {
    status: query.status ?? undefined,
    search: query.search.trim() || undefined,
    include_archived: query.status === null || query.status === "ARCHIVED",
    limit: 100,
    ...SORT[query.sort],
  };
}

/**
 * The workspace list (plan §13, §19). The list and the counts come through useApiResource
 * (account-scoped, aborted when unused, a late answer never shown). Each row is then kept here so
 * a change shows at once:
 *
 * - A status change is applied optimistically, only for a status the server listed in that
 *   item's `allowed_transitions`; while it is in flight the item offers no other change. The
 *   server's answer replaces it (with its new allowed transitions); a failure restores the last
 *   server-confirmed item and is kept for "Try again". Each item numbers its requests, so an
 *   answer to an older request never overwrites a newer state.
 * - Notes, tags and priority are saved and replaced by the server's answer; removal drops the row.
 * - The counts reload after any change that moves them.
 */
export function useWorkspaceList(query: WorkspaceQuery) {
  const filters = workspaceFilters(query);
  const key = `workspace:list:${filters.status ?? "all"}:${filters.sort_by}:${filters.search ?? ""}`;
  const list = useApiResource(key, (signal) => fetchWorkspaceItems(filters, undefined, signal));
  const summary = useApiResource("workspace:summary", (signal) => fetchWorkspaceSummary(undefined, signal));

  const [items, setItems] = useState<WorkspaceItem[] | null>(null);
  const [pending, setPending] = useState<Set<string>>(() => new Set());
  const [failed, setFailed] = useState<FailedChange | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const confirmed = useRef(new Map<string, WorkspaceItem>());
  const requests = useRef(new Map<string, number>());

  useEffect(() => {
    if (!list.data) return;
    setItems(list.data.items);
    confirmed.current = new Map(list.data.items.map((item) => [item.id, item]));
    requests.current = new Map();
    setPending(new Set());
  }, [list.data]);

  const replace = (updated: WorkspaceItem) => setItems((current) => current && current.map((item) => (item.id === updated.id ? updated : item)));
  const setBusy = (id: string, busy: boolean) =>
    setPending((current) => {
      const next = new Set(current);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });

  const changeStatus = useCallback(
    async (item: WorkspaceItem, target: WorkspaceStatus) => {
      // Only a change the server allows for this item, from its confirmed state.
      const base = confirmed.current.get(item.id) ?? item;
      if (!base.allowed_transitions.includes(target)) return;
      const request = (requests.current.get(item.id) ?? 0) + 1;
      requests.current.set(item.id, request);
      setFailed(null);
      setBusy(item.id, true);
      replace({ ...base, status: target, allowed_transitions: [] });
      const title = item.opportunity?.title || "this call";
      try {
        const updated = await transitionWorkspaceStatus(item.id, target);
        if (requests.current.get(item.id) !== request) return;
        confirmed.current.set(item.id, updated);
        replace(updated);
        setAnnouncement(`${title}: ${workspaceStatusMeta(updated.status).label}.`);
        summary.retry();
      } catch {
        if (requests.current.get(item.id) !== request) return;
        replace(base);
        setFailed({ itemId: item.id, title, target });
        setAnnouncement(`${title} could not be moved to ${workspaceStatusMeta(target).label}. It is still ${workspaceStatusMeta(base.status).label}.`);
      } finally {
        if (requests.current.get(item.id) === request) setBusy(item.id, false);
      }
    },
    // summary.retry is stable per key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const update = useCallback(async (item: WorkspaceItem, payload: WorkspaceItemUpdatePayload) => {
    setBusy(item.id, true);
    try {
      const updated = await updateWorkspaceItem(item.id, payload);
      confirmed.current.set(item.id, updated);
      replace(updated);
      return true;
    } catch {
      return false;
    } finally {
      setBusy(item.id, false);
    }
  }, []);

  const remove = useCallback(
    async (item: WorkspaceItem) => {
      setBusy(item.id, true);
      try {
        await removeWorkspaceItem(item.id);
        confirmed.current.delete(item.id);
        setItems((current) => current && current.filter((entry) => entry.id !== item.id));
        setAnnouncement(`Removed ${item.opportunity?.title || "the call"} from your workspace.`);
        summary.retry();
        return true;
      } catch {
        return false;
      } finally {
        setBusy(item.id, false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const retryFailed = useCallback(() => {
    if (!failed) return;
    const item = confirmed.current.get(failed.itemId);
    if (item) void changeStatus(item, failed.target);
  }, [failed, changeStatus]);

  return { list, summary, items, pending, failed, announcement, changeStatus, update, remove, retryFailed, dismissFailed: () => setFailed(null) };
}
