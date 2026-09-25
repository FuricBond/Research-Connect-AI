"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import "../../styles/calendar.css";
import type {
  CalendarEventCreatePayload,
  CalendarEventType,
  ResearchCalendar,
  ResearchCalendarEvent,
} from "../../types/calendar";
import {
  createCalendarEvent,
  deleteCalendarEvent,
  fetchCalendarEvents,
  fetchDefaultCalendar,
  getCalendarExportUrl,
} from "../../services/api";
import {
  AlertCircle,
  AlertTriangle,
  Calendar as CalendarIcon,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  History,
  Info,
  List,
  Loader2,
  Plus,
  RefreshCw,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { RequireAuth } from "../../components/auth/RequireAuth";

type ViewMode = "MONTH" | "AGENDA";

type FilterType = "ALL" | CalendarEventType;

const FILTER_OPTIONS: { label: string; value: FilterType }[] = [
  { label: "All Events", value: "ALL" },
  { label: "Submissions", value: "OPPORTUNITY_SUBMISSION" },
  { label: "Abstracts", value: "ABSTRACT_DEADLINE" },
  { label: "Notifications", value: "NOTIFICATION" },
  { label: "Camera-Ready", value: "CAMERA_READY" },
  { label: "Registration", value: "REGISTRATION" },
  { label: "Conference Dates", value: "EVENT_START" },
  { label: "Milestones", value: "RESEARCH_MILESTONE" },
];

const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function CalendarPage() {
  const [calendar, setCalendar] = useState<ResearchCalendar | null>(null);
  const [events, setEvents] = useState<ResearchCalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // View & Navigation State
  const [viewMode, setViewMode] = useState<ViewMode>("MONTH");
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("ALL");

  // Modals
  const [selectedEvent, setSelectedEvent] = useState<ResearchCalendarEvent | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Form State for User Planning Event
  const [formTitle, setFormTitle] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formType, setFormType] = useState<CalendarEventType>("RESEARCH_MILESTONE");
  const [formDate, setFormDate] = useState("");
  const [formTime, setFormTime] = useState("17:00");
  const [formAllDay, setFormAllDay] = useState(false);

  // Load default calendar & events
  const loadCalendarData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cal = await fetchDefaultCalendar();
      setCalendar(cal);

      const res = await fetchCalendarEvents(cal.id);
      setEvents(res.events);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to load research calendar.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCalendarData();
  }, [loadCalendarData]);

  // Computed Stats
  const stats = useMemo(() => {
    const total = events.length;
    const now = new Date();
    const upcoming = events.filter((ev) => {
      if (!ev.start_datetime) return false;
      return new Date(ev.start_datetime) >= now;
    }).length;
    const conflicts = events.filter((ev) => ev.status === "CONFLICT").length;
    const extensions = events.filter(
      (ev) => ev.provenance_metadata?.latest_revision != null
    ).length;

    return { total, upcoming, conflicts, extensions };
  }, [events]);

  // Filtered Events
  const filteredEvents = useMemo(() => {
    if (selectedFilter === "ALL") return events;
    return events.filter((ev) => ev.event_type === selectedFilter);
  }, [events, selectedFilter]);

  // Navigation handlers
  const handlePrevMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  // Month grid calculation
  const calendarDays = useMemo(() => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();

    const days: {
      date: Date;
      dateStr: string;
      isCurrentMonth: boolean;
      isToday: boolean;
    }[] = [];

    const todayStr = new Date().toISOString().split("T")[0];

    // Previous month padding
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, daysInPrevMonth - i);
      const dStr = d.toISOString().split("T")[0];
      days.push({
        date: d,
        dateStr: dStr,
        isCurrentMonth: false,
        isToday: dStr === todayStr,
      });
    }

    // Current month days
    for (let i = 1; i <= daysInMonth; i++) {
      const d = new Date(year, month, i);
      const dStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(i).padStart(2, "0")}`;
      days.push({
        date: d,
        dateStr: dStr,
        isCurrentMonth: true,
        isToday: dStr === todayStr,
      });
    }

    // Next month padding to reach 35 or 42 cells (5 or 6 weeks)
    const totalCells = days.length <= 35 ? 35 : 42;
    const remaining = totalCells - days.length;
    for (let i = 1; i <= remaining; i++) {
      const d = new Date(year, month + 1, i);
      const dStr = d.toISOString().split("T")[0];
      days.push({
        date: d,
        dateStr: dStr,
        isCurrentMonth: false,
        isToday: dStr === todayStr,
      });
    }

    return days;
  }, [currentDate]);

  // Map events to date string for fast cell lookup
  const eventsByDate = useMemo(() => {
    const map: Record<string, ResearchCalendarEvent[]> = {};
    for (const ev of filteredEvents) {
      let key = ev.date_str;
      if (!key && ev.start_datetime) {
        key = ev.start_datetime.split("T")[0];
      }
      if (key) {
        if (!map[key]) map[key] = [];
        map[key].push(ev);
      }
    }
    return map;
  }, [filteredEvents]);

  // Grouped events for Agenda view
  const agendaGroups = useMemo(() => {
    const groups: { dateStr: string; date: Date; events: ResearchCalendarEvent[] }[] = [];
    const sortedDates = Object.keys(eventsByDate).sort();

    for (const dStr of sortedDates) {
      const dayEvents = eventsByDate[dStr];
      if (dayEvents && dayEvents.length > 0) {
        groups.push({
          dateStr: dStr,
          date: new Date(`${dStr}T00:00:00`),
          events: dayEvents,
        });
      }
    }
    return groups;
  }, [eventsByDate]);

  // Create User Event Handler
  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!calendar || !formTitle || !formDate) return;

    setActionLoading(true);
    try {
      let startDt: string | null = null;
      if (!formAllDay && formTime) {
        startDt = `${formDate}T${formTime}:00Z`;
      }

      const payload: CalendarEventCreatePayload = {
        title: formTitle.trim(),
        description: formDesc.trim() || null,
        event_type: formType,
        date_str: formDate,
        start_datetime: startDt,
        all_day: formAllDay,
      };

      const newEv = await createCalendarEvent(calendar.id, payload);
      setEvents((prev) => [...prev, newEv]);
      setIsAddModalOpen(false);
      setFormTitle("");
      setFormDesc("");
      setFormDate("");
    } catch (err: any) {
      alert(err?.detail || err?.message || "Failed to create planning milestone.");
    } finally {
      setActionLoading(false);
    }
  };

  // Delete User Event Handler
  const handleDeleteEvent = async (eventId: string) => {
    if (!calendar) return;
    if (!confirm("Are you sure you want to remove this planning milestone?")) return;

    setActionLoading(true);
    try {
      await deleteCalendarEvent(calendar.id, eventId);
      setEvents((prev) => prev.filter((ev) => ev.id !== eventId));
      setSelectedEvent(null);
    } catch (err: any) {
      alert(err?.detail || err?.message || "Failed to delete event.");
    } finally {
      setActionLoading(false);
    }
  };

  const currentMonthLabel = currentDate.toLocaleString("default", {
    month: "long",
    year: "numeric",
  });

  return (
    <div className="calendar-container">
      {/* Header */}
      <header className="calendar-header">
        <div className="calendar-header-top">
          <div className="calendar-title-wrap">
            <h1>Research Calendar & Deadline Planning</h1>
            <p className="calendar-tagline">
              Visual planning projection of canonical opportunity deadlines and personal research milestones.
            </p>
          </div>

          <div className="calendar-actions-bar">
            {calendar && (
              <a
                href={getCalendarExportUrl(calendar.id)}
                download="research-calendar.ics"
                className="calendar-export-btn"
                title="Download RFC 5545 iCalendar feed"
              >
                <Download size={15} />
                <span>Export Calendar (.ics)</span>
              </a>
            )}

            <button
              onClick={() => setIsAddModalOpen(true)}
              className="calendar-add-btn"
              title="Create a researcher planning task"
            >
              <Plus size={15} />
              <span>Add Milestone</span>
            </button>
          </div>
        </div>

        {/* Stats Strip */}
        <div className="calendar-stats-strip">
          <div className="calendar-stat-card">
            <span className="calendar-stat-label">Total Events</span>
            <span className="calendar-stat-value">{stats.total}</span>
          </div>
          <div className="calendar-stat-card">
            <span className="calendar-stat-label">Upcoming Deadlines</span>
            <span className="calendar-stat-value">{stats.upcoming}</span>
          </div>
          <div className="calendar-stat-card">
            <span className="calendar-stat-label">Unresolved Conflicts</span>
            <span
              className="calendar-stat-value"
              style={{ color: stats.conflicts > 0 ? "#f87171" : "inherit" }}
            >
              {stats.conflicts}
            </span>
          </div>
          <div className="calendar-stat-card">
            <span className="calendar-stat-label">Deadline Extensions</span>
            <span
              className="calendar-stat-value"
              style={{ color: stats.extensions > 0 ? "#60a5fa" : "inherit" }}
            >
              {stats.extensions}
            </span>
          </div>
        </div>

        {/* Toolbar */}
        <div className="calendar-toolbar">
          <div className="calendar-nav-group">
            <button
              onClick={handlePrevMonth}
              className="calendar-nav-btn"
              aria-label="Previous Month"
            >
              <ChevronLeft size={16} />
            </button>
            <button onClick={handleToday} className="calendar-nav-btn today-btn">
              Today
            </button>
            <button
              onClick={handleNextMonth}
              className="calendar-nav-btn"
              aria-label="Next Month"
            >
              <ChevronRight size={16} />
            </button>
            <span className="calendar-current-label">{currentMonthLabel}</span>
          </div>

          <div className="calendar-view-switcher">
            <button
              className={`calendar-view-btn ${viewMode === "MONTH" ? "active" : ""}`}
              onClick={() => setViewMode("MONTH")}
            >
              Month Grid
            </button>
            <button
              className={`calendar-view-btn ${viewMode === "AGENDA" ? "active" : ""}`}
              onClick={() => setViewMode("AGENDA")}
            >
              Agenda View
            </button>
          </div>
        </div>

        {/* Category Filters */}
        <div className="calendar-filters-row">
          {FILTER_OPTIONS.map((f) => (
            <button
              key={f.value}
              className={`filter-pill ${selectedFilter === f.value ? "active" : ""}`}
              onClick={() => setSelectedFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content */}
      {loading ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "80px 0",
            gap: "12px",
            color: "var(--text-muted)",
          }}
        >
          <Loader2 className="animate-spin" size={32} />
          <p>Loading research calendar & deadline intelligence...</p>
        </div>
      ) : error ? (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            padding: "20px",
            borderRadius: "8px",
            color: "#fca5a5",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <AlertCircle size={20} />
            <strong>Calendar Error</strong>
          </div>
          <p style={{ margin: 0 }}>{error}</p>
          <button
            onClick={loadCalendarData}
            style={{
              marginTop: "12px",
              background: "transparent",
              border: "1px solid #fca5a5",
              color: "#fca5a5",
              padding: "6px 12px",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      ) : viewMode === "MONTH" ? (
        /* Month Grid */
        <div className="month-grid">
          <div className="month-weekdays">
            {WEEKDAY_NAMES.map((wd) => (
              <div key={wd} className="weekday-header">
                {wd}
              </div>
            ))}
          </div>

          <div className="month-days-grid">
            {calendarDays.map((cd, idx) => {
              const dayEvents = eventsByDate[cd.dateStr] || [];
              return (
                <div
                  key={idx}
                  className={`day-cell ${cd.isCurrentMonth ? "" : "other-month"} ${
                    cd.isToday ? "today" : ""
                  }`}
                >
                  <div className="day-cell-top">
                    <span className="day-number">{cd.date.getDate()}</span>
                  </div>

                  <div className="day-events-list">
                    {dayEvents.map((ev) => (
                      <div
                        key={ev.id}
                        className={`event-chip type-${ev.event_type} ${
                          ev.status === "CONFLICT" ? "status-CONFLICT" : ""
                        }`}
                        onClick={() => setSelectedEvent(ev)}
                        title={ev.title}
                      >
                        {ev.provenance_metadata?.latest_revision && "⚡ "}
                        {ev.status === "CONFLICT" && "⚠️ "}
                        {ev.title}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* Agenda View */
        <div className="agenda-view">
          {agendaGroups.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "60px 0",
                background: "var(--bg-card)",
                border: "1px solid var(--border-color)",
                borderRadius: "8px",
                color: "var(--text-muted)",
              }}
            >
              <CalendarIcon size={40} style={{ margin: "0 auto 12px auto", opacity: 0.4 }} />
              <p style={{ margin: 0, fontWeight: 600 }}>No events scheduled for this filter.</p>
              <p style={{ fontSize: "13px", marginTop: "4px" }}>
                Add opportunities to your workspace or create planning milestones to populate your calendar.
              </p>
            </div>
          ) : (
            agendaGroups.map((group) => (
              <div key={group.dateStr} className="agenda-day-group">
                <div className="agenda-day-header">
                  <span className="agenda-day-title">
                    {group.date.toLocaleDateString(undefined, {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </span>
                  <span className="agenda-day-badge">
                    {group.events.length} {group.events.length === 1 ? "event" : "events"}
                  </span>
                </div>

                <div className="agenda-events-list">
                  {group.events.map((ev) => (
                    <div
                      key={ev.id}
                      className="agenda-event-row"
                      onClick={() => setSelectedEvent(ev)}
                    >
                      <div className="agenda-event-left">
                        <span className={`agenda-event-type-badge type-${ev.event_type}`}>
                          {ev.event_type.replace(/_/g, " ")}
                        </span>
                        <div className="agenda-event-info">
                          <span className="agenda-event-title">{ev.title}</span>
                          <span className="agenda-event-sub">
                            {ev.timezone && (
                              <span>
                                <Clock size={12} style={{ display: "inline", marginRight: 4 }} />
                                Timezone: {ev.timezone}
                              </span>
                            )}
                            {ev.is_canonical_projection ? (
                              <span>• Canonical Opportunity Projection</span>
                            ) : (
                              <span>• Researcher Planning Milestone</span>
                            )}
                          </span>
                        </div>
                      </div>

                      <div className="agenda-event-right">
                        {ev.status === "CONFLICT" && (
                          <span className="agenda-pill-warning">Unresolved Conflict</span>
                        )}
                        {ev.provenance_metadata?.latest_revision && (
                          <span className="agenda-pill-extension">Deadline Extended</span>
                        )}
                        <ChevronRight size={16} color="var(--text-muted)" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Event Details Modal */}
      {selectedEvent && (
        <div className="modal-backdrop" onClick={() => setSelectedEvent(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>
                {selectedEvent.is_canonical_projection
                  ? "Opportunity Deadline Intelligence"
                  : "Planning Milestone Details"}
              </h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="modal-close-btn"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span
                  style={{
                    fontSize: "12px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    color: "var(--primary-accent)",
                    letterSpacing: "0.05em",
                  }}
                >
                  {selectedEvent.event_type.replace(/_/g, " ")}
                </span>
                <h2 style={{ margin: 0, fontSize: "20px", color: "var(--text-main)" }}>
                  {selectedEvent.title}
                </h2>
                {selectedEvent.description && (
                  <p style={{ margin: "8px 0 0 0", fontSize: "14px", color: "var(--text-muted)" }}>
                    {selectedEvent.description}
                  </p>
                )}
              </div>

              {/* Conflict Warning */}
              {selectedEvent.status === "CONFLICT" && (
                <div className="conflict-alert">
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700 }}>
                    <AlertTriangle size={16} />
                    <span>Unresolved Deadline Conflict</span>
                  </div>
                  <p style={{ margin: "6px 0 0 0", fontSize: "12px" }}>
                    Multiple primary sources report differing dates for this milestone with equal authority.
                    The deadline remains pending canonical verification.
                  </p>
                </div>
              )}

              {/* Extension Warning */}
              {selectedEvent.provenance_metadata?.latest_revision && (
                <div className="extension-alert">
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700 }}>
                    <History size={16} />
                    <span>Extended Deadline Lineage</span>
                  </div>
                  <p style={{ margin: "6px 0 0 0", fontSize: "12px" }}>
                    {selectedEvent.provenance_metadata.latest_revision.reason ||
                      "This deadline was extended from an earlier date."}
                  </p>
                </div>
              )}

              {/* Provenance Details */}
              <div className="provenance-card">
                <div className="provenance-row">
                  <span className="provenance-label">Milestone Date</span>
                  <span className="provenance-val">
                    {selectedEvent.date_str ||
                      (selectedEvent.start_datetime
                        ? selectedEvent.start_datetime.split("T")[0]
                        : "TBA")}
                  </span>
                </div>

                {selectedEvent.start_datetime && !selectedEvent.all_day && (
                  <div className="provenance-row">
                    <span className="provenance-label">Normalized UTC</span>
                    <span className="provenance-val">{selectedEvent.start_datetime}</span>
                  </div>
                )}

                <div className="provenance-row">
                  <span className="provenance-label">Timezone</span>
                  <span className="provenance-val">
                    {selectedEvent.timezone || "Unspecified / Local"}
                  </span>
                </div>

                <div className="provenance-row">
                  <span className="provenance-label">Provenance Type</span>
                  <span className="provenance-val">
                    {selectedEvent.is_canonical_projection
                      ? "Phase 2.7 Deadline Intelligence (Authoritative)"
                      : "User Planning Task"}
                  </span>
                </div>

                {selectedEvent.provenance_metadata?.opportunity_title && (
                  <div className="provenance-row">
                    <span className="provenance-label">Opportunity</span>
                    <span className="provenance-val">
                      {selectedEvent.provenance_metadata.opportunity_title}
                    </span>
                  </div>
                )}

                {selectedEvent.provenance_metadata?.explanation && (
                  <div className="provenance-row" style={{ flexDirection: "column", gap: 4 }}>
                    <span className="provenance-label">Assessment Explanation</span>
                    <span
                      className="provenance-val"
                      style={{ textAlign: "left", fontSize: "12px", color: "var(--text-muted)" }}
                    >
                      {selectedEvent.provenance_metadata.explanation}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-footer">
              {selectedEvent.opportunity_id && (
                <Link
                  href={`/workspace`}
                  className="btn-secondary"
                  style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6 }}
                >
                  <ExternalLink size={14} />
                  <span>View in Workspace</span>
                </Link>
              )}

              {!selectedEvent.is_canonical_projection && (
                <button
                  onClick={() => handleDeleteEvent(selectedEvent.id)}
                  className="btn-danger"
                  disabled={actionLoading}
                >
                  <Trash2 size={14} style={{ display: "inline", marginRight: 4 }} />
                  <span>Delete Milestone</span>
                </button>
              )}

              <button onClick={() => setSelectedEvent(null)} className="btn-primary">
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Planning Milestone Modal */}
      {isAddModalOpen && (
        <div className="modal-backdrop" onClick={() => setIsAddModalOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={handleCreateEvent}>
              <div className="modal-header">
                <h3>Create Planning Milestone</h3>
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="modal-close-btn"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="modal-body">
                <div className="form-group">
                  <label htmlFor="ev-title">Title *</label>
                  <input
                    id="ev-title"
                    type="text"
                    required
                    placeholder="e.g., Complete literature review or Draft methodology"
                    value={formTitle}
                    onChange={(e) => setFormTitle(e.target.value)}
                    className="form-input"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="ev-type">Category</label>
                  <select
                    id="ev-type"
                    value={formType}
                    onChange={(e) => setFormType(e.target.value as CalendarEventType)}
                    className="form-select"
                  >
                    <option value="RESEARCH_MILESTONE">Research Milestone</option>
                    <option value="CUSTOM">Custom Planning Task</option>
                  </select>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div className="form-group">
                    <label htmlFor="ev-date">Date *</label>
                    <input
                      id="ev-date"
                      type="date"
                      required
                      value={formDate}
                      onChange={(e) => setFormDate(e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="ev-time">Time (UTC)</label>
                    <input
                      id="ev-time"
                      type="time"
                      disabled={formAllDay}
                      value={formTime}
                      onChange={(e) => setFormTime(e.target.value)}
                      className="form-input"
                    />
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    id="ev-allday"
                    type="checkbox"
                    checked={formAllDay}
                    onChange={(e) => setFormAllDay(e.target.checked)}
                  />
                  <label htmlFor="ev-allday" style={{ fontSize: "13px", cursor: "pointer" }}>
                    All-day event (date-only)
                  </label>
                </div>

                <div className="form-group">
                  <label htmlFor="ev-desc">Notes & Description</label>
                  <textarea
                    id="ev-desc"
                    rows={3}
                    placeholder="Preparation notes, target experiments, or collaborator syncs..."
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    className="form-textarea"
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={actionLoading}>
                  {actionLoading ? "Creating..." : "Save Milestone"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}


export default function CalendarPageRoute() {
  return (
    <RequireAuth>
      <CalendarPage  />
    </RequireAuth>
  );
}
