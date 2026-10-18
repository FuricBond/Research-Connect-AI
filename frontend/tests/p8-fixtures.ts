/**
 * P8 — API answers for notifications and their settings, shaped like the backend's
 * (backend/app/schemas/notification.py). Ids are UUIDs, as the API's are, so links are made.
 */

import type { NotificationDeliveryStatus, NotificationItem, NotificationPreference, ReminderRule } from "../types/notification";
import { PROFILE_ID, jsonResponse } from "./factories";

export const WORKSPACE_ITEM_ID = "a1b2c3d4-0000-4000-8000-0000000000aa";
export const POSTING_ID = "b1b2c3d4-0000-4000-8000-0000000000bb";
export const CALL_ID = "c1b2c3d4-0000-4000-8000-0000000000cc";

let counter = 0;

export function makeNotification(overrides: Partial<NotificationItem> = {}): NotificationItem {
  counter += 1;
  const id = `d0000000-0000-4000-8000-${String(counter).padStart(12, "0")}`;
  return {
    id,
    profile_id: PROFILE_ID,
    notification_type: "POSTING_MATCH",
    title: `Notification ${counter}`,
    body: "Something happened.",
    source_type: "RESEARCH_POSTING",
    source_id: POSTING_ID,
    scheduled_for: "2026-10-04T12:00:00+00:00",
    delivered_at: "2026-10-04T12:00:00+00:00",
    read_at: null,
    delivery_status: "DELIVERED",
    delivery_channel: "IN_APP",
    deduplication_key: `dedup-${id}`,
    metadata_json: {},
    email_status: null,
    email_sent_at: null,
    created_at: "2026-10-04T12:00:00+00:00",
    updated_at: "2026-10-04T12:00:00+00:00",
    ...overrides,
  };
}

export const PREFERENCES: NotificationPreference = {
  id: "e0000000-0000-4000-8000-000000000001",
  profile_id: PROFILE_ID,
  email_enabled: true,
  in_app_enabled: true,
  deadline_reminders_enabled: true,
  extension_notifications_enabled: true,
  conflict_notifications_enabled: true,
  calendar_event_reminders_enabled: true,
  posting_match_alerts_enabled: false,
  posting_match_min_score: 60,
  created_at: "2026-10-01T10:00:00+00:00",
  updated_at: "2026-10-01T10:00:00+00:00",
};

export function makeRule(id: string, channel: ReminderRule["delivery_channel"], offset: number, unit: ReminderRule["offset_unit"] = "DAYS"): ReminderRule {
  return {
    id,
    profile_id: PROFILE_ID,
    event_type: null,
    offset_amount: offset,
    offset_unit: unit,
    delivery_channel: channel,
    is_active: true,
    created_at: "2026-10-01T10:00:00+00:00",
    updated_at: "2026-10-01T10:00:00+00:00",
  };
}

export const DELIVERY: NotificationDeliveryStatus = {
  in_app_enabled: true,
  email_enabled: true,
  email_delivery_available: true,
  reminders_scheduled: true,
  reminder_interval_seconds: 300,
};

/** The settings endpoints, for serveShell's `other` routes. Unknown requests fall through. */
export function settingsRoutes(state: {
  preferences?: () => NotificationPreference;
  rules?: () => ReminderRule[];
  delivery?: () => NotificationDeliveryStatus;
  patch?: (body: Record<string, unknown>) => Promise<Response>;
}) {
  return (url: string, init?: RequestInit): Promise<Response> | undefined => {
    const method = init?.method ?? "GET";
    const path = new URL(url).pathname;
    if (path === "/api/v1/notifications/preferences" && method === "GET") return Promise.resolve(jsonResponse(state.preferences?.() ?? PREFERENCES));
    if (path === "/api/v1/notifications/preferences" && method !== "GET") {
      const body = JSON.parse(String(init?.body ?? "{}"));
      return state.patch ? state.patch(body) : Promise.resolve(jsonResponse({ ...(state.preferences?.() ?? PREFERENCES), ...body }));
    }
    if (path === "/api/v1/notifications/rules" && method === "GET") {
      const rules = state.rules?.() ?? [];
      return Promise.resolve(jsonResponse({ rules, total: rules.length }));
    }
    if (path === "/api/v1/notifications/delivery-status") return Promise.resolve(jsonResponse(state.delivery?.() ?? DELIVERY));
    return undefined;
  };
}
