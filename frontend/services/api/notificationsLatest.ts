import type { NotificationListResponse, NotificationType } from "../../types/notification";
import { fetchJson } from "./client";

/** On its own: every signed-in page's bell asks this (hooks/useUnreadNotificationCount.ts). */
export async function fetchNotifications(
  filters?: {
    unreadOnly?: boolean;
    notificationType?: NotificationType;
    limit?: number;
    offset?: number;
  },
  userId?: string,
  signal?: AbortSignal
): Promise<NotificationListResponse> {
  const params = new URLSearchParams();
  if (filters?.unreadOnly !== undefined) params.set("unread_only", String(filters.unreadOnly));
  if (filters?.notificationType) params.set("notification_type", filters.notificationType);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.offset) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<NotificationListResponse>(
    `/api/v1/notifications${qs ? `?${qs}` : ""}`,
    { headers, signal }
  );
}
