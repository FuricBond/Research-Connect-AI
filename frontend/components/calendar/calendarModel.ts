import type { CalendarEventType, ResearchCalendarEvent } from "../../types/calendar";
import { humanizeEnum } from "../../utils/date";

const EVENT_TYPE: Record<string, string> = {
  OPPORTUNITY_SUBMISSION: "Paper submission",
  ABSTRACT_DEADLINE: "Abstract deadline",
  NOTIFICATION: "Notification",
  CAMERA_READY: "Camera-ready",
  REGISTRATION: "Registration",
  EVENT_START: "Event starts",
  EVENT_END: "Event ends",
  RESEARCH_MILESTONE: "Research milestone",
  CUSTOM: "Planning task",
};

export function eventTypeLabel(type: string | null | undefined): string {
  if (!type) return "Event";
  return EVENT_TYPE[type] ?? humanizeEnum(type);
}

export type CalendarFilter = "ALL" | "SUBMISSIONS" | "ABSTRACTS" | "NOTIFICATIONS" | "CAMERA_READY" | "REGISTRATION" | "EVENT" | "MILESTONES";

export const FILTERS: { id: CalendarFilter; label: string; types: CalendarEventType[] | null }[] = [
  { id: "ALL", label: "All", types: null },
  { id: "SUBMISSIONS", label: "Submissions", types: ["OPPORTUNITY_SUBMISSION"] },
  { id: "ABSTRACTS", label: "Abstracts", types: ["ABSTRACT_DEADLINE"] },
  { id: "NOTIFICATIONS", label: "Notifications", types: ["NOTIFICATION"] },
  { id: "CAMERA_READY", label: "Camera-ready", types: ["CAMERA_READY"] },
  { id: "REGISTRATION", label: "Registration", types: ["REGISTRATION"] },
  { id: "EVENT", label: "Conference dates", types: ["EVENT_START", "EVENT_END"] },
  { id: "MILESTONES", label: "Your milestones", types: ["RESEARCH_MILESTONE", "CUSTOM"] },
];

export function matchesFilter(event: ResearchCalendarEvent, filter: CalendarFilter): boolean {
  const types = FILTERS.find((entry) => entry.id === filter)?.types;
  return !types || types.includes(event.event_type);
}

/** The day an event is on, as "YYYY-MM-DD": its date, or the date part of its start. */
export function eventDay(event: ResearchCalendarEvent): string | null {
  if (event.date_str) return event.date_str.slice(0, 10);
  if (event.start_datetime) return event.start_datetime.split("T")[0];
  return null;
}

export const isExtended = (event: ResearchCalendarEvent) => event.provenance_metadata?.latest_revision != null;
export const isDisputed = (event: ResearchCalendarEvent) => event.status === "CONFLICT";

/** "YYYY-MM-DD" of a local date. */
export function dayKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** "YYYY-MM" of a month, as kept in the address (`?month=2026-10`). */
export function monthKey(date: Date): string {
  return dayKey(date).slice(0, 7);
}

export function parseMonth(value: string | null, fallback: Date): Date {
  const match = value?.match(/^(\d{4})-(\d{2})$/);
  if (!match) return new Date(fallback.getFullYear(), fallback.getMonth(), 1);
  const month = Number(match[2]) - 1;
  if (month < 0 || month > 11) return new Date(fallback.getFullYear(), fallback.getMonth(), 1);
  return new Date(Number(match[1]), month, 1);
}

export function shiftMonth(month: Date, by: number): Date {
  return new Date(month.getFullYear(), month.getMonth() + by, 1);
}

/** A local date from "YYYY-MM-DD", at noon so no time zone moves it to another day. */
export function dayDate(key: string): Date {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

export interface MonthCell {
  key: string;
  date: Date;
  inMonth: boolean;
}

/** The weeks shown for a month, Sunday first (as before), each a row of seven days. */
export function monthWeeks(month: Date): MonthCell[][] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1, 12);
  const lead = first.getDay(); // days before the 1st, counting from Sunday
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - lead, 12);
  const weeks: MonthCell[][] = [];
  for (let week = 0; week < 6; week++) {
    const row: MonthCell[] = [];
    for (let day = 0; day < 7; day++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + week * 7 + day, 12);
      row.push({ key: dayKey(date), date, inMonth: date.getMonth() === month.getMonth() });
    }
    if (week >= 4 && !row.some((cell) => cell.inMonth)) break;
    weeks.push(row);
  }
  return weeks;
}

/** The time of an event in words, with its zone; date-only and all-day events have none. */
export function eventTime(event: ResearchCalendarEvent): string | null {
  if (event.all_day || !event.start_datetime || !event.start_datetime.includes("T")) return null;
  const date = new Date(event.start_datetime);
  if (Number.isNaN(date.getTime())) return null;
  const zone = event.timezone || "UTC";
  try {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: zone, timeZoneName: "short" });
  } catch {
    return `${date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC`;
  }
}
