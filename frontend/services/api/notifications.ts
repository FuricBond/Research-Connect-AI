import type { NotificationDeliveryStatus, NotificationItem, NotificationListResponse, NotificationPreference, NotificationPreferenceUpdate, NotificationType, NotificationUnreadCountResponse, ReminderRule, ReminderRuleCreate, ReminderRuleListResponse, ReminderRuleUpdate, ReminderRunSummary } from "../../types/notification";
import { fetchJson } from "./client";

// ── Phase 4.5 — Deadline Reminders & Notifications API ───────────────────────

export async function fetchNotificationUnreadCount(
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationUnreadCountResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationUnreadCountResponse>(
    `/api/v1/notifications/unread-count`,
    { headers, signal }
  );
}

/** Phase 5.16: whether in-app and email delivery are on, and whether reminders are scheduled. */
export async function fetchNotificationDeliveryStatus(
  signal?: AbortSignal
): Promise<NotificationDeliveryStatus> {
  return fetchJson<NotificationDeliveryStatus>(`/api/v1/notifications/delivery-status`, { signal });
}

export async function markNotificationAsRead(
  notificationId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationItem> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationItem>(
    `/api/v1/notifications/${notificationId}/read`,
    { method: "POST", headers, signal }
  );
}

export async function markAllNotificationsAsRead(
  userId?: string,
  signal?: AbortSignal
): Promise<{ marked_read_count: number }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ marked_read_count: number }>(
    `/api/v1/notifications/read-all`,
    { method: "POST", headers, signal }
  );
}

export async function fetchNotificationPreferences(
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationPreference> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationPreference>(
    `/api/v1/notifications/preferences`,
    { headers, signal }
  );
}

export async function updateNotificationPreferences(
  payload: NotificationPreferenceUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationPreference> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<NotificationPreference>(
    `/api/v1/notifications/preferences`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function fetchReminderRules(
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRuleListResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRuleListResponse>(
    `/api/v1/notifications/rules`,
    { headers, signal }
  );
}

export async function createReminderRule(
  payload: ReminderRuleCreate,
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRule> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRule>(
    `/api/v1/notifications/rules`,
    { method: "POST", headers, body: JSON.stringify(payload), signal }
  );
}

export async function updateReminderRule(
  ruleId: string,
  payload: ReminderRuleUpdate,
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRule> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRule>(
    `/api/v1/notifications/rules/${ruleId}`,
    { method: "PATCH", headers, body: JSON.stringify(payload), signal }
  );
}

export async function deleteReminderRule(
  ruleId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  await fetchJson<void>(`/api/v1/notifications/rules/${ruleId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function triggerReminderScheduler(
  userId?: string,
  signal?: AbortSignal
): Promise<ReminderRunSummary> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ReminderRunSummary>(
    `/api/v1/notifications/trigger-reminders`,
    { method: "POST", headers, signal }
  );
}
