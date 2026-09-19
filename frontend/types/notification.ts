/**
 * Phase 4.5 — Deadline Reminders, Notifications & Scheduled Alerts Types.
 */

export type NotificationType =
  | "DEADLINE_UPCOMING"
  | "DEADLINE_TODAY"
  | "DEADLINE_EXTENDED"
  | "DEADLINE_MOVED_EARLIER"
  | "DEADLINE_CONFLICT"
  | "CALENDAR_EVENT_UPCOMING"
  | "SUBMISSION_STATUS_CHANGE"
  | "SYSTEM";

export type DeliveryChannel = "IN_APP" | "EMAIL" | "PUSH";

export type DeliveryStatus = "PENDING" | "DELIVERED" | "FAILED" | "CANCELLED" | "SKIPPED";

export type OffsetUnit = "MINUTES" | "HOURS" | "DAYS" | "WEEKS";

export interface NotificationItem {
  id: string;
  profile_id: string;
  notification_type: NotificationType;
  title: string;
  body: string;
  source_type: string;
  source_id?: string | null;
  opportunity_id?: string | null;
  calendar_event_id?: string | null;
  submission_id?: string | null;
  deadline_type?: string | null;
  scheduled_for: string;
  delivered_at?: string | null;
  read_at?: string | null;
  delivery_status: DeliveryStatus;
  delivery_channel: DeliveryChannel;
  deduplication_key: string;
  metadata_json: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface NotificationUnreadCountResponse {
  profile_id: string;
  unread_count: number;
}

export interface NotificationPreference {
  id: string;
  profile_id: string;
  email_enabled: boolean;
  in_app_enabled: boolean;
  deadline_reminders_enabled: boolean;
  extension_notifications_enabled: boolean;
  conflict_notifications_enabled: boolean;
  calendar_event_reminders_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationPreferenceUpdate {
  email_enabled?: boolean;
  in_app_enabled?: boolean;
  deadline_reminders_enabled?: boolean;
  extension_notifications_enabled?: boolean;
  conflict_notifications_enabled?: boolean;
  calendar_event_reminders_enabled?: boolean;
}

export interface ReminderRule {
  id: string;
  profile_id: string;
  event_type?: string | null;
  offset_amount: number;
  offset_unit: OffsetUnit;
  delivery_channel: DeliveryChannel;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReminderRuleCreate {
  event_type?: string | null;
  offset_amount: number;
  offset_unit: OffsetUnit;
  delivery_channel?: DeliveryChannel;
  is_active?: boolean;
}

export interface ReminderRuleUpdate {
  event_type?: string | null;
  offset_amount?: number;
  offset_unit?: OffsetUnit;
  delivery_channel?: DeliveryChannel;
  is_active?: boolean;
}

export interface ReminderRuleListResponse {
  rules: ReminderRule[];
  total: number;
}

export interface ReminderRunSummary {
  discovered_reminders: number;
  created_notifications: number;
  delivered_notifications: number;
  skipped_duplicates: number;
  cancelled_obsolete: number;
  errors: string[];
  executed_at: string;
}
