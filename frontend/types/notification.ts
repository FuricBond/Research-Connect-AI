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
  | "SYSTEM"
  | "POSTING_MATCH";

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
  /** Phase 5.16: the email copy. Null until decided. */
  email_status?: EmailStatus | null;
  email_sent_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type EmailStatus = "SENT" | "RETRY" | "FAILED" | "SKIPPED";

export interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface NotificationUnreadCountResponse {
  /** Phase 5.16: null for a user without a research profile (the count is then 0). */
  profile_id: string | null;
  unread_count: number;
}

/** Phase 5.16: how notifications actually reach the signed-in user. */
export interface NotificationDeliveryStatus {
  in_app_enabled: boolean;
  /** The user's own Email Alerts switch. */
  email_enabled: boolean;
  /** The server emails notifications and may mail this user's address. */
  email_delivery_available: boolean;
  reminders_scheduled: boolean;
  reminder_interval_seconds: number | null;
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
  /** Phase 5.15: alert when a newly published posting fits; off by default. */
  posting_match_alerts_enabled: boolean;
  /** Minimum fit (0-100) for that alert; 60 by default. */
  posting_match_min_score: number;
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
  posting_match_alerts_enabled?: boolean;
  posting_match_min_score?: number;
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
