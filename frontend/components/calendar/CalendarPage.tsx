"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Download, History, Plus } from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { useApiResource } from "../../hooks/useApiResource";
import { createCalendarEvent, deleteCalendarEvent, downloadCalendarIcs, fetchCalendarEvents, fetchDefaultCalendar } from "../../services/api";
import type { CalendarEventType, ResearchCalendarEvent } from "../../types/calendar";
import { cx } from "../../utils/cx";
import { callHref } from "../research/OpportunityCard";
import { Button, IconButton } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";
import { Checkbox, Select, TextArea, TextInput } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { actionError } from "../workspace/workflow";
import {
  FILTERS,
  dayDate,
  dayKey,
  eventDay,
  eventTime,
  eventTypeLabel,
  isDisputed,
  isExtended,
  matchesFilter,
  monthKey,
  monthWeeks,
  parseMonth,
  shiftMonth,
  type CalendarFilter,
} from "./calendarModel";
import styles from "./Calendar.module.css";

type View = "agenda" | "month";
const PHONE = "(max-width: 767.98px)";
const WEEKDAYS: [short: string, long: string][] = [
  ["Sun", "Sunday"],
  ["Mon", "Monday"],
  ["Tue", "Tuesday"],
  ["Wed", "Wednesday"],
  ["Thu", "Thursday"],
  ["Fri", "Friday"],
  ["Sat", "Saturday"],
];

/** The view when the address does not name one: the agenda on phones (plan §16), else the month. */
function defaultView(): View {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "month";
  return window.matchMedia(PHONE).matches ? "agenda" : "month";
}

const longDay = (key: string) => dayDate(key).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

/**
 * P7 — /calendar: the deadlines of the calls you track (projected by the calendar service) and
 * your own milestones, by month. The agenda (a list by day) is the default on phones, the month
 * grid on wider screens; either can be chosen, and the month, view and filter are in the address
 * (`?view=month&month=2026-11&type=SUBMISSIONS`). Events open a dialog with their source, time
 * zone, extensions and disputes, and a link to the call. The .ics export is unchanged.
 */
export function CalendarPage() {
  const [params, go] = useAddressSearch();
  const [fallbackView] = useState<View>(defaultView);
  const [today] = useState(() => new Date());
  const view: View = params.get("view") === "agenda" ? "agenda" : params.get("view") === "month" ? "month" : fallbackView;
  const month = parseMonth(params.get("month"), today);
  const filterParam = params.get("type");
  const filter: CalendarFilter = FILTERS.some((entry) => entry.id === filterParam) ? (filterParam as CalendarFilter) : "ALL";

  const calendar = useApiResource("calendar:default", (signal) => fetchDefaultCalendar(undefined, signal));
  const calendarId = calendar.data?.id ?? null;
  const loaded = useApiResource(calendarId ? `calendar:${calendarId}:events` : null, (signal) => fetchCalendarEvents(calendarId as string, {}, undefined, signal));
  const [events, setEvents] = useState<ResearchCalendarEvent[] | null>(null);
  useEffect(() => {
    // The list is `items`. A partial body shows "no events" rather than taking the page down.
    if (loaded.data) setEvents(loaded.data.items ?? []);
  }, [loaded.data]);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [open, setOpen] = useState<ResearchCalendarEvent | null>(null);
  const [adding, setAdding] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const href = (next: { view?: View; month?: Date; filter?: CalendarFilter }) => {
    const query = new URLSearchParams();
    const nextView = next.view ?? (params.get("view") as View | null);
    if (nextView) query.set("view", nextView);
    const nextMonth = next.month ?? month;
    if (monthKey(nextMonth) !== monthKey(today)) query.set("month", monthKey(nextMonth));
    const nextFilter = next.filter ?? filter;
    if (nextFilter !== "ALL") query.set("type", nextFilter);
    const text = query.toString();
    return `/calendar${text ? `?${text}` : ""}`;
  };

  const all = useMemo(() => events ?? [], [events]);
  const shown = useMemo(() => all.filter((event) => matchesFilter(event, filter)), [all, filter]);
  const byDay = useMemo(() => {
    const map = new Map<string, ResearchCalendarEvent[]>();
    for (const event of shown) {
      const key = eventDay(event);
      if (!key) continue;
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [shown]);
  const prefix = monthKey(month);
  const monthDays = [...byDay.keys()].filter((key) => key.startsWith(prefix)).sort();
  const todayKey = dayKey(today);
  const upcoming = all.filter((event) => (eventDay(event) ?? "") >= todayKey).length;
  const disputed = all.filter(isDisputed).length;
  const extended = all.filter(isExtended).length;
  const nextAfter = [...byDay.keys()].filter((key) => key > `${prefix}-31`).sort()[0] ?? null;
  const lastBefore = [...byDay.keys()].filter((key) => key < `${prefix}-01`).sort().pop() ?? null;
  const monthLabel = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  const exportIcs = async () => {
    if (!calendarId) return;
    setExporting(true);
    setExportError(null);
    try {
      await downloadCalendarIcs(calendarId);
    } catch (err) {
      setExportError((err as { detail?: string; message?: string })?.detail || (err as Error)?.message || "The calendar could not be exported.");
    } finally {
      setExporting(false);
    }
  };

  const failedToLoad = calendar.status === "error" || loaded.status === "error";
  const retry = () => (calendar.status === "error" ? calendar.retry() : loaded.retry());

  return (
    <>
      <PageHeader
        title="Calendar"
        description="The deadlines of the calls you track and your own research milestones."
        actions={
          // Always there (disabled until the calendar is known), so the page does not move when it is.
          <div className={styles.headerActions}>
            <Button variant="secondary" leadingIcon={<Download size={16} aria-hidden="true" />} loading={exporting} disabled={!calendarId || exporting} onClick={() => void exportIcs()}>
              {exporting ? "Exporting…" : "Export calendar (.ics)"}
            </Button>
            <Button leadingIcon={<Plus size={16} aria-hidden="true" />} disabled={!calendarId} onClick={() => setAdding(true)}>
              Add milestone
            </Button>
          </div>
        }
      />
      {exportError && (
        <Alert tone="danger" announce className={styles.alert}>
          {exportError}
        </Alert>
      )}
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>

      {failedToLoad ? (
        <ErrorState title="Your calendar could not be loaded" kind={(calendar.error ?? loaded.error)?.kind === "network" ? "offline" : "failed"} onRetry={retry} />
      ) : events === null ? (
        <SkeletonList rows={4} lines={2} label="Loading your calendar" />
      ) : (
        <>
          {(upcoming > 0 || disputed > 0 || extended > 0) && (
            <p className={styles.summary}>
              <span>
                {upcoming} upcoming {upcoming === 1 ? "date" : "dates"}
              </span>
              {disputed > 0 && (
                <span className={styles.flag}>
                  <AlertTriangle size={14} aria-hidden="true" /> {disputed} {disputed === 1 ? "date is" : "dates are"} disputed between sources
                </span>
              )}
              {extended > 0 && (
                <span className={styles.flag}>
                  <History size={14} aria-hidden="true" /> {extended} {extended === 1 ? "deadline was" : "deadlines were"} extended
                </span>
              )}
            </p>
          )}

          <div className={styles.chips} role="group" aria-label="Show events of type">
            {FILTERS.map((entry) => {
              const count = entry.id === "ALL" ? all.length : all.filter((event) => matchesFilter(event, entry.id)).length;
              if (count === 0 && entry.id !== "ALL" && entry.id !== filter) return null;
              return (
                <button key={entry.id} type="button" className={styles.chip} aria-pressed={entry.id === filter} onClick={() => go(href({ filter: entry.id }))}>
                  <span>
                    {entry.label}
                    <span className={styles.chipCount}> ({count})</span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className={styles.toolbar}>
            <div className={styles.nav}>
              <IconButton variant="secondary" label="Previous month" icon={<ChevronLeft size={16} aria-hidden="true" />} onClick={() => go(href({ month: shiftMonth(month, -1) }))} />
              <Button variant="secondary" onClick={() => go(href({ month: today }))} disabled={monthKey(month) === monthKey(today)}>
                Today
              </Button>
              <IconButton variant="secondary" label="Next month" icon={<ChevronRight size={16} aria-hidden="true" />} onClick={() => go(href({ month: shiftMonth(month, 1) }))} />
              <h2 className={styles.month} aria-live="polite">
                {monthLabel}
              </h2>
            </div>
            <div className={styles.views} role="group" aria-label="View">
              <button type="button" className={styles.viewButton} aria-pressed={view === "agenda"} onClick={() => go(href({ view: "agenda" }))}>
                Agenda
              </button>
              <button type="button" className={styles.viewButton} aria-pressed={view === "month"} onClick={() => go(href({ view: "month" }))}>
                Month
              </button>
            </div>
          </div>

          {view === "agenda" ? (
            monthDays.length === 0 ? (
              <EmptyState
                variant={all.length === 0 ? "first-use" : "no-results"}
                title={all.length === 0 ? "Your calendar is empty." : `Nothing in ${monthLabel}.`}
                description={
                  all.length === 0
                    ? "Add a call's dates from its page, or add your own milestones."
                    : nextAfter
                      ? `The next date is ${longDay(nextAfter)}.`
                      : lastBefore
                        ? `The last date was ${longDay(lastBefore)}.`
                        : undefined
                }
                actions={
                  all.length === 0 ? (
                    <Link href="/browse" className={styles.link}>
                      Browse calls for papers
                    </Link>
                  ) : nextAfter ? (
                    <Button variant="secondary" onClick={() => go(href({ month: dayDate(nextAfter) }))}>
                      Go to {dayDate(nextAfter).toLocaleDateString(undefined, { month: "long", year: "numeric" })}
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <ol className={styles.agenda} aria-label={`Events in ${monthLabel}`}>
                {monthDays.map((key) => (
                  <li key={key} className={styles.agendaDay}>
                    <h3 className={cx(styles.agendaDate, key === todayKey && styles.agendaToday)}>
                      {longDay(key)}
                      {key === todayKey && <span className={styles.todayWord}> · Today</span>}
                    </h3>
                    <ul className={styles.agendaEvents}>
                      {(byDay.get(key) ?? []).map((event) => (
                        <li key={event.id}>
                          <EventButton event={event} onOpen={setOpen} />
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            )
          ) : (
            <>
              <table className={styles.grid}>
                <caption className="rc-visually-hidden">{monthLabel}: days with events have a button that lists them below the calendar.</caption>
                <thead>
                  <tr>
                    {WEEKDAYS.map(([short, long]) => (
                      <th key={short} scope="col" abbr={long}>
                        {short}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {monthWeeks(month).map((week) => (
                    <tr key={week[0].key}>
                      {week.map((cell) => {
                        const dayEvents = byDay.get(cell.key) ?? [];
                        const isToday = cell.key === todayKey;
                        return (
                          <td key={cell.key} className={cx(styles.cell, !cell.inMonth && styles.outside, isToday && styles.today, selectedDay === cell.key && styles.selected)}>
                            {dayEvents.length > 0 ? (
                              <button
                                type="button"
                                className={styles.dayButton}
                                aria-pressed={selectedDay === cell.key}
                                aria-label={`${longDay(cell.key)}${isToday ? ", today" : ""}: ${dayEvents.length} ${dayEvents.length === 1 ? "event" : "events"}`}
                                onClick={() => setSelectedDay((current) => (current === cell.key ? null : cell.key))}
                              >
                                <span className={styles.dayNumber}>{cell.date.getDate()}</span>
                                <span className={styles.dayTitles} aria-hidden="true">
                                  {dayEvents.slice(0, 2).map((event) => (
                                    <span key={event.id} className={cx(styles.dayTitle, !event.is_canonical_projection && styles.own)}>
                                      {event.title}
                                    </span>
                                  ))}
                                  {dayEvents.length > 2 && <span className={styles.more}>+{dayEvents.length - 2} more</span>}
                                </span>
                                <span className={styles.dayCount} aria-hidden="true">
                                  {dayEvents.length}
                                </span>
                              </button>
                            ) : (
                              <span className={styles.dayNumber}>
                                <span aria-hidden="true">{cell.date.getDate()}</span>
                                <span className="rc-visually-hidden">
                                  {longDay(cell.key)}
                                  {isToday ? ", today" : ""}
                                </span>
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {selectedDay && (byDay.get(selectedDay)?.length ?? 0) > 0 ? (
                <section className={styles.dayPanel} aria-labelledby="calendar-day-heading">
                  <h3 id="calendar-day-heading" className={styles.agendaDate}>
                    {longDay(selectedDay)}
                  </h3>
                  <ul className={styles.agendaEvents}>
                    {(byDay.get(selectedDay) ?? []).map((event) => (
                      <li key={event.id}>
                        <EventButton event={event} onOpen={setOpen} />
                      </li>
                    ))}
                  </ul>
                </section>
              ) : (
                monthDays.length === 0 && (
                  <p className={styles.hint}>
                    {all.length === 0 ? "Your calendar is empty: add a call's dates from its page, or add your own milestones." : `Nothing in ${monthLabel}.`}
                    {nextAfter && ` The next date is ${longDay(nextAfter)}.`}
                  </p>
                )
              )}
            </>
          )}
        </>
      )}

      {calendarId && (
        <>
          <EventDetails
            event={open}
            calendarId={calendarId}
            onClose={() => setOpen(null)}
            onDeleted={(event) => {
              setEvents((current) => current && current.filter((entry) => entry.id !== event.id));
              setOpen(null);
              setMessage(`Deleted the milestone ${event.title}.`);
            }}
          />
          <AddMilestone
            open={adding}
            calendarId={calendarId}
            onClose={() => setAdding(false)}
            onAdded={(event) => {
              setEvents((current) => [...(current ?? []), event]);
              setAdding(false);
              setMessage(`Added the milestone ${event.title}.`);
              const key = eventDay(event);
              if (key) go(href({ month: dayDate(key) }));
            }}
          />
        </>
      )}
    </>
  );
}

/** An event as a row: its kind, title, time and flags; opens its details. */
function EventButton({ event, onOpen }: { event: ResearchCalendarEvent; onOpen: (event: ResearchCalendarEvent) => void }) {
  const time = eventTime(event);
  return (
    <button type="button" className={cx(styles.event, !event.is_canonical_projection && styles.own)} onClick={() => onOpen(event)}>
      <span className={styles.eventKind}>{eventTypeLabel(event.event_type)}</span>
      <span className={styles.eventTitle}>{event.title}</span>
      <span className={styles.eventMeta}>
        {time && <span>{time}</span>}
        <span>{event.is_canonical_projection ? event.provenance_metadata?.opportunity_venue || "From a call you track" : "Your milestone"}</span>
        {isExtended(event) && (
          <span className={styles.flag}>
            <History size={14} aria-hidden="true" /> Extended
          </span>
        )}
        {isDisputed(event) && (
          <span className={styles.flag}>
            <AlertTriangle size={14} aria-hidden="true" /> Date disputed
          </span>
        )}
      </span>
    </button>
  );
}

function EventDetails({ event, calendarId, onClose, onDeleted }: { event: ResearchCalendarEvent | null; calendarId: string; onClose: () => void; onDeleted: (event: ResearchCalendarEvent) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forId, setForId] = useState<string | null>(null);
  if ((event?.id ?? null) !== forId) {
    setForId(event?.id ?? null);
    setConfirming(false);
    setError(null);
  }

  const remove = async () => {
    if (!event || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteCalendarEvent(calendarId, event.id);
      onDeleted(event);
    } catch (err) {
      setError(actionError(err, "The milestone could not be deleted."));
    } finally {
      setDeleting(false);
    }
  };

  const key = event ? eventDay(event) : null;
  const time = event ? eventTime(event) : null;
  const meta = event?.provenance_metadata;
  const revision = meta?.latest_revision as { reason?: string } | null | undefined;
  const opportunityId = event?.opportunity_id || meta?.opportunity_id;

  return (
    <Dialog
      open={event !== null}
      onClose={onClose}
      title={event?.title ?? ""}
      description={event ? eventTypeLabel(event.event_type) : undefined}
      footer={
        confirming ? (
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
            <Button variant="danger" loading={deleting} onClick={() => void remove()}>
              Delete milestone
            </Button>
          </>
        ) : (
          <>
            {event && !event.is_canonical_projection && (
              <Button variant="ghost" onClick={() => setConfirming(true)}>
                Delete milestone
              </Button>
            )}
            <Button onClick={onClose}>Done</Button>
          </>
        )
      }
    >
      {event && (
        <div className={styles.details}>
          {confirming && (
            <Alert tone="warning" title={`Delete "${event.title}"?`}>
              It is removed from your calendar and from future exports. This cannot be undone.
            </Alert>
          )}
          {error && (
            <Alert tone="danger" announce>
              {error}
            </Alert>
          )}
          {isDisputed(event) && (
            <Alert tone="warning" title="Sources disagree on this date">
              Equally authoritative sources give different dates; it is not confirmed yet.
            </Alert>
          )}
          {isExtended(event) && (
            <Alert tone="info" title="This deadline was extended">
              {revision?.reason || "It was moved from an earlier date."}
            </Alert>
          )}
          {event.description && <p className={styles.text}>{event.description}</p>}
          <dl className={styles.facts}>
            <div>
              <dt>Date</dt>
              <dd>{key ? longDay(key) : "Not announced"}</dd>
            </div>
            {time && (
              <div>
                <dt>Time</dt>
                <dd>{time}</dd>
              </div>
            )}
            <div>
              <dt>Source</dt>
              <dd>{event.is_canonical_projection ? "The call's official dates" : "Your planning milestone"}</dd>
            </div>
            {meta?.opportunity_title && (
              <div>
                <dt>Call</dt>
                <dd>{meta.opportunity_title}</dd>
              </div>
            )}
          </dl>
          {meta?.explanation && <p className={styles.text}>{meta.explanation}</p>}
          {opportunityId && (
            <p className={styles.links}>
              <Link href={callHref(opportunityId)} className={styles.link}>
                Open the call for papers
              </Link>
              <Link href="/workspace" className={styles.link}>
                Open your workspace
              </Link>
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}

const KINDS: { value: CalendarEventType; label: string }[] = [
  { value: "RESEARCH_MILESTONE", label: "Research milestone" },
  { value: "CUSTOM", label: "Planning task" },
];

function AddMilestone({ open, calendarId, onClose, onAdded }: { open: boolean; calendarId: string; onClose: () => void; onAdded: (event: ResearchCalendarEvent) => void }) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<CalendarEventType>("RESEARCH_MILESTONE");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("17:00");
  const [allDay, setAllDay] = useState(false);
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<{ title?: string; date?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const dateRef = useRef<HTMLInputElement>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const next: { title?: string; date?: string } = {};
    if (!title.trim()) next.title = "Give the milestone a title.";
    if (!date) next.date = "Choose its date.";
    setErrors(next);
    if (next.title) return titleRef.current?.focus();
    if (next.date) return dateRef.current?.focus();
    submitting.current = true;
    setSaving(true);
    setError(null);
    try {
      const created = await createCalendarEvent(calendarId, {
        title: title.trim(),
        description: notes.trim() || null,
        event_type: kind,
        date_str: date,
        start_datetime: !allDay && time ? `${date}T${time}:00Z` : null,
        all_day: allDay,
      });
      setTitle("");
      setNotes("");
      setDate("");
      onAdded(created);
    } catch (err) {
      // Everything typed stays; "Add milestone" can be pressed again.
      setError(actionError(err, "The milestone could not be added."));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a milestone"
      initialFocusRef={titleRef}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="calendar-add-milestone" loading={saving}>
            Add milestone
          </Button>
        </>
      }
    >
      <form id="calendar-add-milestone" className={styles.form} onSubmit={(event) => void submit(event)} noValidate>
        {error && (
          <Alert tone="danger" announce>
            {error}
          </Alert>
        )}
        <TextInput
          ref={titleRef}
          label="Title"
          required
          maxLength={255}
          value={title}
          error={errors.title}
          hint="For example: Finish the related-work section."
          onChange={(event) => {
            setTitle(event.target.value);
            if (errors.title) setErrors((current) => ({ ...current, title: undefined }));
          }}
        />
        <Select label="Kind" value={kind} onChange={(event) => setKind(event.target.value as CalendarEventType)}>
          {KINDS.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </Select>
        <div className={styles.formRow}>
          <TextInput
            ref={dateRef}
            label="Date"
            type="date"
            required
            value={date}
            error={errors.date}
            onChange={(event) => {
              setDate(event.target.value);
              if (errors.date) setErrors((current) => ({ ...current, date: undefined }));
            }}
          />
          <TextInput label="Time (UTC)" type="time" value={time} disabled={allDay} onChange={(event) => setTime(event.target.value)} />
        </div>
        <Checkbox label="All day (no time)" checked={allDay} onChange={(event) => setAllDay(event.target.checked)} />
        <TextArea label="Notes" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
      </form>
    </Dialog>
  );
}
