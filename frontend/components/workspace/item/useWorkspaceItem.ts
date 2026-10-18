"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApiResource, type ApiResource } from "../../../hooks/useApiResource";
import { fetchWorkspaceItem, transitionWorkspaceStatus, updateWorkspaceItem } from "../../../services/api";
import type { WorkspaceItem, WorkspaceItemUpdatePayload, WorkspaceStatus } from "../../../types/workspace";
import { workspaceStatusMeta } from "../../../utils/status";

/**
 * The last answer a resource gave, kept while it reloads after a change, so a list does not
 * blink back to a skeleton each time something in it is saved.
 */
export function useKept<T>(resource: ApiResource<T>): T | undefined {
  const kept = useRef<T | undefined>(undefined);
  if (resource.data !== undefined) kept.current = resource.data;
  return resource.data ?? (resource.status === "loading" ? kept.current : undefined);
}

/**
 * One workspace item by id (GET /workspace/{id}: its owner or any member may read it). Its status
 * changes the way the list's do (useWorkspaceList): only to a status the server listed in
 * `allowed_transitions`, shown at once, replaced by the server's answer, rolled back to the last
 * confirmed item on failure, and an answer to an older request never overwrites a newer state.
 */
export function useWorkspaceItem(id: string | null) {
  const resource = useApiResource(id ? `workspace:item:${id}` : null, (signal) => fetchWorkspaceItem(id as string, undefined, signal));
  const [item, setItem] = useState<WorkspaceItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<WorkspaceStatus | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const confirmed = useRef<WorkspaceItem | null>(null);
  const request = useRef(0);

  useEffect(() => {
    if (!resource.data) return;
    confirmed.current = resource.data;
    request.current += 1;
    setItem(resource.data);
    setSaving(false);
  }, [resource.data]);

  const changeStatus = useCallback(async (target: WorkspaceStatus) => {
    const base = confirmed.current;
    if (!base || !base.allowed_transitions.includes(target)) return;
    const mine = ++request.current;
    setFailed(null);
    setSaving(true);
    setItem({ ...base, status: target, allowed_transitions: [] });
    try {
      const updated = await transitionWorkspaceStatus(base.id, target);
      if (request.current !== mine) return;
      confirmed.current = updated;
      setItem(updated);
      setAnnouncement(`Status: ${workspaceStatusMeta(updated.status).label}.`);
    } catch {
      if (request.current !== mine) return;
      setItem(base);
      setFailed(target);
      setAnnouncement(`It could not be moved to ${workspaceStatusMeta(target).label}. It is still ${workspaceStatusMeta(base.status).label}.`);
    } finally {
      if (request.current === mine) setSaving(false);
    }
  }, []);

  const update = useCallback(async (_item: WorkspaceItem, payload: WorkspaceItemUpdatePayload) => {
    const base = confirmed.current;
    if (!base) return false;
    setSaving(true);
    try {
      const updated = await updateWorkspaceItem(base.id, payload);
      confirmed.current = updated;
      setItem(updated);
      return true;
    } catch {
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  const retryFailed = useCallback(() => {
    if (failed) void changeStatus(failed);
  }, [failed, changeStatus]);

  return { resource, item, saving, failed, announcement, changeStatus, update, retryFailed, dismissFailed: () => setFailed(null), reload: resource.retry };
}
