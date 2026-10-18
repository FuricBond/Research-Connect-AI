"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Bell,
  CalendarDays,
  CheckCheck,
  ClipboardCheck,
  ClipboardList,
  Clock,
  FileText,
  Megaphone,
  RefreshCw,
  Settings,
  Sparkles,
  UserCheck,
  UserCog,
  UserMinus,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useAddressSearch } from "../../hooks/useAddressSearch";
import { useApiResource } from "../../hooks/useApiResource";
import { UNREAD_POLL_MS, notifyNotificationsChanged } from "../../hooks/useUnreadNotificationCount";
import { fetchNotifications, markAllNotificationsAsRead, markNotificationAsRead, triggerReminderScheduler } from "../../services/api";
import type { NotificationItem, NotificationType } from "../../types/notification";
import { FILTERABLE_TYPES, groupBySource, notificationHref, notificationTime, notificationTypeLabel } from "../../utils/notifications";
import { useSession } from "../auth/SessionProvider";
import { Button, ButtonLink } from "../ui/Button/Button";
import { Select } from "../ui/Field/Field";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { Alert, EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { ChipCount } from "../workspace/ChipCount";
import { actionError } from "../workspace/workflow";
import { useKept } from "../workspace/item/useWorkspaceItem";
import styles from "./Notifications.module.css";

const PAGE = 50;
const MAX = 200; // the API's largest page

/** A picture for each kind (decorative: the kind is also said in words). */
const ICONS: Record<string, LucideIcon> = {
  DEADLINE_TODAY: AlertTriangle,
  DEADLINE_UPCOMING: Clock,
  DEADLINE_EXTENDED: Sparkles,
  DEADLINE_MOVED_EARLIER: Clock,
  DEADLINE_CONFLICT: AlertTriangle,
  CALENDAR_EVENT_UPCOMING: CalendarDays,
  WORKSPACE_INVITATION: UserPlus,
  INVITATION_ACCEPTED: UserCheck,
  MEMBER_ROLE_CHANGED: UserCog,
  MEMBER_REMOVED: UserMinus,
  TASK_ASSIGNED: ClipboardList,
  TASK_COMPLETED: ClipboardCheck,
  DOCUMENT_UPDATED: FileText,
  COLLABORATION_ACTIVITY: Users,
  POSTING_MATCH: Megaphone,
};

export function readNotificationFilters(params: URLSearchParams): { unreadOnly: boolean; type: NotificationType | null } {
  const type = params.get("type");
  return {
    unreadOnly: params.get("show") === "unread",
    type: type && FILTERABLE_TYPES.includes(type) ? (type as NotificationType) : null,
  };
}

function filtersHref(unreadOnly: boolean, type: string | null): string {
  const params = new URLSearchParams();
  if (unreadOnly) params.set("show", "unread");
  if (type) params.set("type", type);
  const text = params.toString();
  return `/notifications${text ? `?${text}` : ""}`;
}

/**
 * P8 — /notifications (plan §16: a grouped list, buttons rather than swipes, the time under the
 * title). Notifications are grouped by where they come from — calls for papers, the calendar, the
 * workspace, research postings — newest first within each group. "All" or "Unread" and the kind
 * are in the address. The list refreshes quietly every 30 seconds while the tab is visible
 * (Phase 5.16), keeping what is on screen. Delivery details (channels, reminder schedule) live in
 * Settings → Notifications, not on each notification.
 */
export function NotificationsPage() {
  const { hasRole } = useSession();
  const isAdmin = hasRole("ADMIN");
  const [params, go] = useAddressSearch();
  const { unreadOnly, type } = readNotificationFilters(params);
  const [limit, setLimit] = useState(PAGE);
  const filterKey = `${unreadOnly}:${type ?? "all"}`;
  const seenFilter = useRef(filterKey);
  if (seenFilter.current !== filterKey) {
    seenFilter.current = filterKey;
    if (limit !== PAGE) setLimit(PAGE);
  }

  const list = useApiResource(`notifications:list:${filterKey}:${limit}`, (signal) =>
    fetchNotifications({ unreadOnly, notificationType: type ?? undefined, limit }, undefined, signal)
  );
  const shown = useKept(list);
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [unread, setUnread] = useState<number | null>(null);
  useEffect(() => {
    if (!shown) return;
    setItems(shown.notifications);
    setUnread(shown.unread_count);
  }, [shown]);

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [checking, setChecking] = useState(false);

  // Phase 5.16: new notifications appear without a reload while the tab is visible.
  const { retry } = list;
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") retry();
    }, UNREAD_POLL_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") retry();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [retry]);

  const markRead = async (item: NotificationItem) => {
    if (busy) return;
    setBusy(item.id);
    setError(null);
    try {
      const updated = await markNotificationAsRead(item.id);
      const readAt = updated?.read_at ?? new Date().toISOString();
      setItems((current) => current && (unreadOnly ? current.filter((entry) => entry.id !== item.id) : current.map((entry) => (entry.id === item.id ? { ...entry, read_at: readAt } : entry))));
      setUnread((count) => (count === null ? count : Math.max(0, count - 1)));
      setMessage(`Marked “${item.title}” as read.`);
      notifyNotificationsChanged();
    } catch (err) {
      setError(actionError(err, "It could not be marked as read."));
    } finally {
      setBusy(null);
    }
  };

  const markAllRead = async () => {
    if (busy) return;
    setBusy("all");
    setError(null);
    try {
      await markAllNotificationsAsRead();
      const now = new Date().toISOString();
      setItems((current) => current && (unreadOnly ? [] : current.map((entry) => ({ ...entry, read_at: entry.read_at ?? now }))));
      setUnread(0);
      setMessage("All notifications are marked as read.");
      notifyNotificationsChanged();
    } catch (err) {
      setError(actionError(err, "They could not be marked as read."));
    } finally {
      setBusy(null);
    }
  };

  // The reminder pass is an administrator action (the API answers 403 to others).
  const checkReminders = async () => {
    setChecking(true);
    setError(null);
    try {
      await triggerReminderScheduler();
      retry();
      notifyNotificationsChanged();
      setMessage("Reminders checked.");
    } catch (err) {
      setError(actionError(err, "The reminder check did not run."));
    } finally {
      setChecking(false);
    }
  };

  const total = shown?.total ?? null;
  const groups = items ? groupBySource(items) : [];

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Deadline reminders and updates about your work, grouped by where they come from."
        actions={
          <div className={styles.actions}>
            {unread !== null && unread > 0 && (
              <Button variant="secondary" leadingIcon={<CheckCheck size={16} aria-hidden="true" />} loading={busy === "all"} onClick={() => void markAllRead()}>
                Mark all as read
              </Button>
            )}
            {isAdmin && (
              <Button variant="secondary" leadingIcon={<RefreshCw size={16} aria-hidden="true" />} loading={checking} disabled={checking} onClick={() => void checkReminders()}>
                Check reminders now
              </Button>
            )}
            <ButtonLink href="/settings#notifications" variant="ghost" leadingIcon={<Settings size={16} aria-hidden="true" />}>
              Notification settings
            </ButtonLink>
          </div>
        }
      />

      <div className={styles.toolbar}>
        <div className={styles.chips} role="group" aria-label="Show">
          <button type="button" className={styles.chip} aria-pressed={!unreadOnly} onClick={() => go(filtersHref(false, type))}>
            <span>
              All
              <ChipCount count={!unreadOnly ? total : null} />
            </span>
          </button>
          <button type="button" className={styles.chip} aria-pressed={unreadOnly} onClick={() => go(filtersHref(true, type))}>
            <span>
              Unread
              <ChipCount count={unread} />
            </span>
          </button>
        </div>
        <Select label="Kind" value={type ?? ""} onChange={(event) => go(filtersHref(unreadOnly, event.target.value || null))} className={styles.kind}>
          <option value="">All kinds</option>
          {FILTERABLE_TYPES.map((value) => (
            <option key={value} value={value}>
              {notificationTypeLabel(value)}
            </option>
          ))}
        </Select>
      </div>

      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce className={styles.alert}>
          {error}
        </Alert>
      )}

      {items === null ? (
        list.status === "error" ? (
          <ErrorState headingLevel={2} title="Your notifications could not be loaded" kind={list.error?.kind === "network" ? "offline" : "failed"} onRetry={retry} />
        ) : (
          <SkeletonList rows={4} lines={2} label="Loading your notifications" />
        )
      ) : items.length === 0 ? (
        unreadOnly ? (
          <EmptyState headingLevel={2} variant="done" title="You're all caught up." description="Nothing unread." />
        ) : type ? (
          <EmptyState
            headingLevel={2}
            variant="no-results"
            title={`No notifications of the kind “${notificationTypeLabel(type)}”.`}
            actions={
              <Button variant="secondary" onClick={() => go(filtersHref(false, null))}>
                Show all notifications
              </Button>
            }
          />
        ) : (
          <EmptyState headingLevel={2} title="No notifications yet." description="Deadline reminders, workspace activity and posting updates appear here." />
        )
      ) : (
        <div className={styles.groups} aria-busy={list.status === "loading" || undefined}>
          {groups.map((group) => (
            <section key={group.key} className={styles.group} aria-labelledby={`notifications-${group.key}`}>
              <h2 id={`notifications-${group.key}`} className={styles.groupTitle}>
                {group.label}
                <span className={styles.groupCount}> ({group.items.length})</span>
              </h2>
              <ul className={styles.list}>
                {group.items.map((item) => (
                  <NotificationRow key={item.id} item={item} busy={busy === item.id} onRead={() => void markRead(item)} />
                ))}
              </ul>
            </section>
          ))}
          {total !== null && total > items.length && (
            <div className={styles.more}>
              {limit < MAX ? (
                <Button variant="secondary" loading={list.status === "loading"} onClick={() => setLimit((current) => Math.min(MAX, current + PAGE))}>
                  Show older notifications
                </Button>
              ) : (
                <p className={styles.meta}>
                  Showing the latest {items.length} of {total}.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function NotificationRow({ item, busy, onRead }: { item: NotificationItem; busy: boolean; onRead: () => void }) {
  const unread = !item.read_at;
  const href = notificationHref(item);
  const titleId = `notification-${item.id}`;
  const Icon = ICONS[item.notification_type] ?? Bell;
  const time = notificationTime(item.created_at);
  return (
    <li className={`${styles.item} ${unread ? styles.unread : ""} notification-card`} aria-labelledby={titleId}>
      <span className={styles.icon} aria-hidden="true">
        <Icon size={18} />
      </span>
      <div className={styles.body}>
        <p className={styles.kind}>{notificationTypeLabel(item.notification_type)}</p>
        <h3 id={titleId} className={styles.title}>
          {href ? <Link href={href}>{item.title}</Link> : item.title}
        </h3>
        <p className={styles.meta}>
          {time && <time dateTime={item.created_at}>{time}</time>}
          {unread && (
            <span className={styles.unreadMark}>
              <span className={styles.dot} aria-hidden="true" />
              Unread
            </span>
          )}
          {item.email_status === "SENT" && <span>Also emailed</span>}
        </p>
        {item.body && <p className={styles.text}>{item.body}</p>}
      </div>
      {unread && (
        <div className={styles.rowActions}>
          <Button size="sm" variant="ghost" loading={busy} aria-describedby={titleId} onClick={onRead}>
            Mark as read
          </Button>
        </div>
      )}
    </li>
  );
}
