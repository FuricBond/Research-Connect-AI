import { getAuthHeaders } from "../auth";
import type { CalendarCreatePayload, CalendarEventCreatePayload, CalendarEventFilterParams, CalendarEventListResponse, CalendarEventUpdatePayload, CalendarUpdatePayload, OpportunityProjectPayload, OpportunityProjectResponse, ResearchCalendar, ResearchCalendarEvent, ResearcherCalendarViewResponse } from "../../types/calendar";
import { API_URL, ApiError, extractErrorDetail, fetchJson, notifyUnauthorized } from "./client";

// ── Phase 4.4 — Research Calendar & Visual Planning API ──────────────────────────

export async function fetchDefaultCalendar(
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>("/api/v1/calendar/default", { headers, signal });
}

export async function fetchCalendars(
  userId?: string,
  signal?: AbortSignal
): Promise<{ calendars: ResearchCalendar[]; total: number }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ calendars: ResearchCalendar[]; total: number }>("/api/v1/calendar", {
    headers,
    signal,
  });
}

export async function createCalendar(
  payload: CalendarCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>("/api/v1/calendar", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchCalendar(
  calendarId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>(`/api/v1/calendar/${calendarId}`, { headers, signal });
}

export async function updateCalendar(
  calendarId: string,
  payload: CalendarUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendar> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendar>(`/api/v1/calendar/${calendarId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function fetchCalendarEvents(
  calendarId: string,
  filters: CalendarEventFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<CalendarEventListResponse> {
  const params = new URLSearchParams();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.opportunity_id) params.set("opportunity_id", filters.opportunity_id);
  if (filters.submission_id) params.set("submission_id", filters.submission_id);

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/calendar/${calendarId}/events?${qs}`
    : `/api/v1/calendar/${calendarId}/events`;

  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<CalendarEventListResponse>(endpoint, {
    headers,
    signal,
  });
}

export async function createCalendarEvent(
  calendarId: string,
  payload: CalendarEventCreatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendarEvent> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendarEvent>(`/api/v1/calendar/${calendarId}/events`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateCalendarEvent(
  calendarId: string,
  eventId: string,
  payload: CalendarEventUpdatePayload,
  userId?: string,
  signal?: AbortSignal
): Promise<ResearchCalendarEvent> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<ResearchCalendarEvent>(`/api/v1/calendar/${calendarId}/events/${eventId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
    signal,
  });
}

export async function deleteCalendarEvent(
  calendarId: string,
  eventId: string,
  userId?: string,
  signal?: AbortSignal
): Promise<{ message: string }> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  return fetchJson<{ message: string }>(`/api/v1/calendar/${calendarId}/events/${eventId}`, {
    method: "DELETE",
    headers,
    signal,
  });
}

export async function projectOpportunityToCalendar(
  calendarId: string,
  payload: OpportunityProjectPayload,
  userId?: string,
  signal?: AbortSignal
): Promise<OpportunityProjectResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;
  const q = new URLSearchParams();
  if (payload.submission_id) q.set("submission_id", payload.submission_id);
  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<OpportunityProjectResponse>(
    `/api/v1/calendar/${calendarId}/opportunities/${payload.opportunity_id}/project${queryStr}`,
    {
      method: "POST",
      headers,
      signal,
    }
  );
}

export async function fetchResearcherCalendar(
  researcherId: string,
  filters: CalendarEventFilterParams = {},
  userId?: string,
  signal?: AbortSignal
): Promise<ResearcherCalendarViewResponse> {
  const params = new URLSearchParams();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.opportunity_id) params.set("opportunity_id", filters.opportunity_id);
  if (filters.submission_id) params.set("submission_id", filters.submission_id);

  const qs = params.toString();
  const endpoint = qs
    ? `/api/v1/researchers/${researcherId}/calendar?${qs}`
    : `/api/v1/researchers/${researcherId}/calendar`;

  const headers: Record<string, string> = {};
  if (userId) headers["X-User-ID"] = userId;

  return fetchJson<ResearcherCalendarViewResponse>(endpoint, { headers, signal });
}

/**
 * Downloads a research calendar as `research-calendar.ics`.
 *
 * The export needs the caller's credentials, so it is fetched with the auth headers and saved
 * from a Blob; a plain link would send no Bearer token and always be refused.
 */
export async function downloadCalendarIcs(calendarId: string, signal?: AbortSignal): Promise<void> {
  const path = `/api/v1/calendar/${calendarId}/export.ics`;
  const headers = getAuthHeaders();

  const response = await fetch(`${API_URL}${path}`, { headers, signal });
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      detail = extractErrorDetail(await response.json(), detail);
    } catch {
      // Non-JSON error body fallback
    }
    if (response.status === 401) {
      notifyUnauthorized(path, headers["Authorization"] !== undefined);
    }
    throw new ApiError(response.status, detail, detail);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "research-calendar.ics";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function getResearcherCalendarExportUrl(researcherId: string, userId?: string): string {
  const base = `${API_URL}/api/v1/researchers/${researcherId}/calendar.ics`;
  if (userId) {
    return `${base}?user_id=${encodeURIComponent(userId)}`;
  }
  return base;
}
