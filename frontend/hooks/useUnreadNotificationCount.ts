"use client";

/**
 * Phase 5.16 — the signed-in user's unread notification count, kept current.
 *
 * Asks the API every 30 seconds while the tab is visible, at once when the tab comes back into
 * view or regains focus, and whenever a page announces a change with
 * `notifyNotificationsChanged()` (for example after marking notifications read). A hidden tab
 * makes no requests. A failed request keeps the last count; the next tick tries again.
 *
 * Audit FUNC-11: one request answers both the count and the latest three notifications, which the
 * dashboard's "Notifications" module reads from here (plan §8: "shared with the bell").
 */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fetchNotifications } from "../services/api";
import type { NotificationItem } from "../types/notification";

export const NOTIFICATIONS_CHANGED_EVENT = "notifications:changed";
export const UNREAD_POLL_MS = 30_000;

const LATEST_SHOWN = 3;

export interface LatestNotificationsAnswer {
  unread: number;
  items: NotificationItem[];
  /** The request failed and no answer has come yet. */
  failed?: boolean;
}

let latest: LatestNotificationsAnswer | null = null;
const listeners = new Set<() => void>();

export function publishLatest(answer: LatestNotificationsAnswer | null): void {
  latest = answer;
  listeners.forEach((listener) => listener());
}

/** What the shell's last request said: null until it answers. Makes no request of its own. */
export function useLatestNotifications(): LatestNotificationsAnswer | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => latest,
    () => null
  );
}

/** Tells every listener (the shell's notification bell, the notifications page) to refresh now. */
export function notifyNotificationsChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
}

/** The unread count, or null until the first answer (and whenever `enabled` is false). */
export function useUnreadNotificationCount(enabled: boolean): number | null {
  const [count, setCount] = useState<number | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (document.visibilityState === "hidden") return;
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    try {
      const response = await fetchNotifications({ limit: LATEST_SHOWN }, undefined, controller.signal);
      if (controller.signal.aborted) return;
      setCount(response.unread_count);
      publishLatest({ unread: response.unread_count, items: response.notifications });
    } catch {
      // Keep the last count; the next tick tries again.
      if (!controller.signal.aborted && latest === null) publishLatest({ unread: 0, items: [], failed: true });
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setCount(null);
      publishLatest(null);
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), UNREAD_POLL_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const onRefresh = () => void refresh();
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", onRefresh);
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, onRefresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", onRefresh);
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, onRefresh);
      inFlight.current?.abort();
      publishLatest(null);
    };
  }, [enabled, refresh]);

  return count;
}
