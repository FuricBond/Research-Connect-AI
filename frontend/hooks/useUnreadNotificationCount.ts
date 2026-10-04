"use client";

/**
 * Phase 5.16 — the signed-in user's unread notification count, kept current.
 *
 * Asks the API every 30 seconds while the tab is visible, at once when the tab comes back into
 * view or regains focus, and whenever a page announces a change with
 * `notifyNotificationsChanged()` (for example after marking notifications read). A hidden tab
 * makes no requests. A failed request keeps the last count; the next tick tries again.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchNotificationUnreadCount } from "../services/api";

export const NOTIFICATIONS_CHANGED_EVENT = "notifications:changed";
export const UNREAD_POLL_MS = 30_000;

/** Tells every listener (the navbar badge, the notifications page) to refresh now. */
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
      const response = await fetchNotificationUnreadCount(undefined, controller.signal);
      if (!controller.signal.aborted) setCount(response.unread_count);
    } catch {
      // Keep the last count; the next tick tries again.
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setCount(null);
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
    };
  }, [enabled, refresh]);

  return count;
}
