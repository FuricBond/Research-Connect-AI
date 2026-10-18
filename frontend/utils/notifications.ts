/**
 * P8 — notification words, grouping and destinations, in one place.
 *
 * The API sends enum values (`DEADLINE_UPCOMING`, `RESEARCH_POSTING`); the interface shows words.
 * A value this map does not know yet is said in plain words, never as the raw identifier.
 */
import type { DeliveryChannel, NotificationItem } from "../types/notification";
import { humanizeEnum } from "./date";
import { isUuid } from "./ids";

/** Each `notification_type` the backend allows (chk_notifications_type), as a reader would say it. */
const TYPE_LABELS: Record<string, string> = {
  DEADLINE_UPCOMING: "Deadline coming up",
  DEADLINE_TODAY: "Due today",
  DEADLINE_EXTENDED: "Deadline extended",
  DEADLINE_MOVED_EARLIER: "Deadline moved earlier",
  DEADLINE_CONFLICT: "Sources disagree on a deadline",
  CALENDAR_EVENT_UPCOMING: "Calendar event coming up",
  SUBMISSION_STATUS_CHANGE: "Submission status changed",
  SYSTEM: "Update",
  WORKSPACE_INVITATION: "Workspace invitation",
  INVITATION_ACCEPTED: "Invitation accepted",
  MEMBER_ROLE_CHANGED: "Role changed",
  MEMBER_REMOVED: "Removed from workspace",
  TASK_ASSIGNED: "Task assigned",
  TASK_COMPLETED: "Task completed",
  DOCUMENT_UPDATED: "Document updated",
  COLLABORATION_ACTIVITY: "Workspace activity",
  POSTING_MATCH: "A posting that fits you",
};

/** The types offered in the list's filter, in the order a reader looks for them. */
export const FILTERABLE_TYPES = Object.keys(TYPE_LABELS);

export function notificationTypeLabel(type: string | null | undefined): string {
  if (!type) return "Notification";
  return TYPE_LABELS[type] ?? humanizeEnum(type);
}

/** Each `source_type` the backend writes (reminder scheduler, collaboration, postings, alerts). */
const SOURCE_LABELS: Record<string, string> = {
  OPPORTUNITY: "Calls for papers",
  CALENDAR_EVENT: "Calendar",
  WORKSPACE: "Workspace",
  RESEARCH_POSTING: "Research postings",
  SYSTEM: "System",
};

/** A source this list does not know yet goes under "Other updates", never under its raw name. */
export const OTHER_SOURCE_LABEL = "Other updates";

export function notificationSourceLabel(source: string | null | undefined): string {
  return (source && SOURCE_LABELS[source]) || OTHER_SOURCE_LABEL;
}

const CHANNEL_LABELS: Record<string, string> = {
  IN_APP: "In the app",
  EMAIL: "By email",
  PUSH: "Push (not available yet)",
};

export function deliveryChannelLabel(channel: DeliveryChannel | string | null | undefined): string {
  if (!channel) return "In the app";
  return CHANNEL_LABELS[channel] ?? humanizeEnum(channel);
}

export interface NotificationGroup {
  /** The group's key: the known source, or "OTHER". */
  key: string;
  label: string;
  items: NotificationItem[];
}

/**
 * Groups notifications by where they come from, keeping the API's order (newest first) inside
 * each group; groups come in the order of their newest notification. Unknown sources share one
 * "Other updates" group.
 */
export function groupBySource(items: readonly NotificationItem[]): NotificationGroup[] {
  const groups = new Map<string, NotificationGroup>();
  for (const item of items) {
    const known = item.source_type && SOURCE_LABELS[item.source_type] ? item.source_type : "OTHER";
    let group = groups.get(known);
    if (!group) {
      group = { key: known, label: notificationSourceLabel(known === "OTHER" ? null : known), items: [] };
      groups.set(known, group);
    }
    group.items.push(item);
  }
  return [...groups.values()];
}

/**
 * Where a notification leads, or null when there is nowhere to go. Only ids that can be the API's
 * are linked; the destination page checks access (a workspace item opens for its members, P7).
 */
export function notificationHref(item: NotificationItem): string | null {
  if (item.source_type === "WORKSPACE" && isUuid(item.source_id)) return `/workspace/${encodeURIComponent(item.source_id)}`;
  if (item.source_type === "RESEARCH_POSTING" && isUuid(item.source_id)) return `/postings/${encodeURIComponent(item.source_id)}`;
  if (item.source_type === "CALENDAR_EVENT" || item.calendar_event_id) return "/calendar";
  if (isUuid(item.opportunity_id)) return `/calls/${encodeURIComponent(item.opportunity_id)}`;
  return null;
}

/** "18 Oct, 14:05" (with the year when it is not this year), in the reader's time zone. */
export function notificationTime(iso: string | null | undefined, now = new Date()): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
  });
}
