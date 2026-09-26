/**
 * Phase 4.4 — Research Calendar & Visual Deadline Planning Types.
 */

export type CalendarEventType =
  | "OPPORTUNITY_SUBMISSION"
  | "ABSTRACT_DEADLINE"
  | "NOTIFICATION"
  | "CAMERA_READY"
  | "REGISTRATION"
  | "EVENT_START"
  | "EVENT_END"
  | "RESEARCH_MILESTONE"
  | "CUSTOM";

export type CalendarEventStatus =
  | "ACTIVE"
  | "COMPLETED"
  | "CANCELLED"
  | "SUPERSEDED"
  | "CONFLICT";

export interface ResearchCalendar {
  id: string;
  user_id: string;
  profile_id?: string | null;
  name: string;
  description?: string | null;
  timezone: string;
  is_default: boolean;
  event_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResearchCalendarEvent {
  id: string;
  calendar_id: string;
  opportunity_id?: string | null;
  submission_id?: string | null;
  title: string;
  description?: string | null;
  event_type: CalendarEventType;
  start_datetime?: string | null;
  end_datetime?: string | null;
  date_str?: string | null;
  all_day: boolean;
  timezone?: string | null;
  is_canonical_projection: boolean;
  provenance_metadata: {
    opportunity_id?: string;
    opportunity_title?: string;
    opportunity_venue?: string;
    milestone_type?: string;
    conflict_state?: string;
    confidence?: number;
    explanation?: string;
    raw_value?: string;
    authority_tier?: number;
    latest_revision?: Record<string, any> | null;
    revision_count?: number;
    unresolved_alternatives_count?: number;
    [key: string]: any;
  };
  status: CalendarEventStatus;
  created_at: string;
  updated_at: string;
}

/**
 * `GET /api/v1/calendar/{calendar_id}/events`. Mirrors the backend's
 * CalendarEventListResponse (backend/app/schemas/calendar.py), where both fields are
 * required. The list is `items`, not `events`.
 */
export interface CalendarEventListResponse {
  items: ResearchCalendarEvent[];
  total: number;
}

export interface CalendarCreatePayload {
  name: string;
  description?: string | null;
  timezone?: string;
  is_default?: boolean;
}

export interface CalendarUpdatePayload {
  name?: string;
  description?: string | null;
  timezone?: string;
  is_default?: boolean;
}

export interface CalendarEventCreatePayload {
  title: string;
  description?: string | null;
  event_type?: CalendarEventType;
  start_datetime?: string | null;
  end_datetime?: string | null;
  date_str?: string | null;
  all_day?: boolean;
  timezone?: string | null;
}

export interface CalendarEventUpdatePayload {
  title?: string;
  description?: string | null;
  event_type?: CalendarEventType;
  start_datetime?: string | null;
  end_datetime?: string | null;
  date_str?: string | null;
  all_day?: boolean;
  timezone?: string | null;
  status?: CalendarEventStatus;
}

export interface CalendarEventFilterParams {
  start_date?: string;
  end_date?: string;
  event_type?: CalendarEventType;
  opportunity_id?: string;
  submission_id?: string;
}

export interface OpportunityProjectPayload {
  opportunity_id: string;
  submission_id?: string | null;
}

export interface OpportunityProjectResponse {
  opportunity_id: string;
  calendar_id: string;
  projected_events: ResearchCalendarEvent[];
  created_count: number;
  updated_count: number;
  unchanged_count: number;
}

export interface ResearcherCalendarViewResponse {
  calendar: ResearchCalendar;
  events: ResearchCalendarEvent[];
  total_events: number;
  upcoming_deadlines_count: number;
  conflict_count: number;
  extension_count: number;
}
