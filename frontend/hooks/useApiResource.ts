"use client";

/**
 * P4 — one way for a page to load an API resource (FRONTEND_REDESIGN_PLAN.md §18, §25).
 *
 *   const calls = useApiResource("workspace:by-deadline", (signal) => fetchWorkspaceItems(…, signal), {
 *     isEmpty: (data) => data.items.length === 0,
 *   });
 *   // calls.status: "idle" | "loading" | "success" | "empty" | "error"
 *
 * - `key` names what is loaded, including every parameter that changes the answer. `null` means
 *   "not yet" (a request that waits for another one's answer): nothing is requested, the status
 *   is "idle". `load` is an existing services/api.ts function; it gets an AbortSignal.
 * - `data` always belongs to the current key: when the key changes, the previous key's answer is
 *   never shown as the new one's (the status goes back to "loading").
 * - "empty" is a successful answer with nothing to show (`isEmpty`), never a failure. "error"
 *   carries only a classification ({ kind, status }), never the server's text, so nothing
 *   internal can reach the screen; the page words the message.
 * - Sharing: components that use the same key at the same time share one request and its answer
 *   (the dashboard's deadlines and its timeline both read the workspace). Entries belong to the
 *   signed-in account (the user id is part of the key) and are dropped when the last component
 *   using them unmounts: there is no cache across pages or accounts. A request nobody needs any
 *   more is aborted, and an answer that arrives after its request was replaced is ignored.
 * - `retry()` asks again, for everyone using the key. Nothing retries on its own.
 * - P5: `scope: "public"` is for data that is the same for everyone (calls for papers, papers):
 *   it loads for visitors too, and from the first render rather than after the session check.
 *   Its entries are shared by whoever is on the page and dropped like any other.
 *
 * A 401 is still reported to the session by the API client, which signs the browser out.
 */

import { useCallback, useMemo, useRef, useSyncExternalStore } from "react";
import { useSession } from "../components/auth/SessionProvider";
import { ApiError } from "../services/api";

export type ResourceStatus = "idle" | "loading" | "success" | "empty" | "error";

export interface ResourceError {
  kind: "network" | "unauthorized" | "forbidden" | "not-found" | "server" | "other";
  /** The HTTP status, or null when the server was not reached. */
  status: number | null;
}

export interface ApiResource<T> {
  status: ResourceStatus;
  /** The current key's answer ("success" and "empty" only). */
  data: T | undefined;
  error: ResourceError | null;
  /** How many times retry() has been asked for this key (0 on the first load). */
  retries: number;
  retry: () => void;
}

/** One immutable value per state change, so React sees every change (including a retry's). */
type Snapshot =
  | { status: "loading"; retries: number }
  | { status: "success"; data: unknown; retries: number }
  | { status: "error"; error: ResourceError; retries: number };

interface Entry {
  snapshot: Snapshot;
  controller: AbortController | null;
  listeners: Set<() => void>;
  load: (signal: AbortSignal) => Promise<unknown>;
}

const LOADING: Snapshot = { status: "loading", retries: 0 };
const entries = new Map<string, Entry>();

function classify(error: unknown): ResourceError {
  if (error instanceof ApiError) {
    const status = error.status;
    if (status === 401) return { kind: "unauthorized", status };
    if (status === 403) return { kind: "forbidden", status };
    if (status === 404) return { kind: "not-found", status };
    if (status >= 500) return { kind: "server", status };
    return { kind: "other", status };
  }
  return { kind: "network", status: null };
}

function publish(entry: Entry, snapshot: Snapshot) {
  entry.snapshot = snapshot;
  for (const listener of [...entry.listeners]) listener();
}

/** Starts (or restarts) the entry's request; a newer request makes the older one's answer void. */
function start(key: string, entry: Entry, retries: number) {
  entry.controller?.abort();
  const controller = new AbortController();
  entry.controller = controller;
  if (entry.snapshot.status !== "loading" || entry.snapshot.retries !== retries) publish(entry, retries === 0 ? LOADING : { status: "loading", retries });
  entry.load(controller.signal).then(
    (data) => {
      if (entry.controller !== controller || entries.get(key) !== entry) return;
      entry.controller = null;
      publish(entry, { status: "success", data, retries });
    },
    (error: unknown) => {
      if (entry.controller !== controller || entries.get(key) !== entry) return;
      entry.controller = null;
      publish(entry, { status: "error", error: classify(error), retries });
    }
  );
}

function subscribe(key: string, load: () => (signal: AbortSignal) => Promise<unknown>, listener: () => void) {
  let entry = entries.get(key);
  if (!entry) {
    entry = { snapshot: LOADING, controller: null, listeners: new Set(), load: load() };
    entries.set(key, entry);
    start(key, entry, 0);
  }
  entry.listeners.add(listener);
  const subscribed = entry;
  return () => {
    subscribed.listeners.delete(listener);
    // Released at the end of the current task, so a component that unsubscribes and subscribes
    // again in the same commit (React's development double effects) keeps its request.
    queueMicrotask(() => {
      if (subscribed.listeners.size > 0 || entries.get(key) !== subscribed) return;
      subscribed.controller?.abort();
      entries.delete(key);
    });
  };
}

/** How many resources are held right now (for tests: nothing outlives the components using it). */
export function heldApiResources(): number {
  return entries.size;
}

export function useApiResource<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
  options: { isEmpty?: (data: T) => boolean; scope?: "account" | "public" } = {}
): ApiResource<T> {
  const { user } = useSession();
  // The account is part of the identity: one account's answers are never another's. Public data
  // has one identity for everyone, so it does not wait for (or change with) the session.
  const owner = options.scope === "public" ? "public" : (user?.id ?? null);
  const scopedKey = key === null || owner === null ? null : `${owner}::${key}`;

  // The latest loader and emptiness test, without making them part of the identity.
  const loadRef = useRef(load);
  loadRef.current = load;
  const isEmptyRef = useRef(options.isEmpty);
  isEmptyRef.current = options.isEmpty;

  const subscribeToKey = useCallback(
    (listener: () => void) => {
      if (scopedKey === null) return () => undefined;
      return subscribe(scopedKey, () => (signal) => loadRef.current(signal), listener);
    },
    [scopedKey]
  );
  const getSnapshot = useCallback(() => (scopedKey === null ? null : (entries.get(scopedKey)?.snapshot ?? LOADING)), [scopedKey]);
  const snapshot = useSyncExternalStore(subscribeToKey, getSnapshot, getSnapshot);

  const retry = useCallback(() => {
    if (scopedKey === null) return;
    const entry = entries.get(scopedKey);
    if (entry) start(scopedKey, entry, entry.snapshot.retries + 1);
  }, [scopedKey]);

  return useMemo<ApiResource<T>>(() => {
    if (snapshot === null) return { status: "idle", data: undefined, error: null, retries: 0, retry };
    const { retries } = snapshot;
    if (snapshot.status === "loading") return { status: "loading", data: undefined, error: null, retries, retry };
    if (snapshot.status === "error") return { status: "error", data: undefined, error: snapshot.error, retries, retry };
    const data = snapshot.data as T;
    const empty = isEmptyRef.current?.(data) ?? false;
    return { status: empty ? "empty" : "success", data, error: null, retries, retry };
  }, [snapshot, retry]);
}
