"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Bell } from "lucide-react";
import { useApiResource } from "../../hooks/useApiResource";
import { useUnreadNotificationCount } from "../../hooks/useUnreadNotificationCount";
import { fetchNotifications } from "../../services/api";
import { groupBySource, notificationHref, notificationTime } from "../../utils/notifications";
import { NOTIFICATIONS_HREF } from "../../utils/navigation";
import { Disclosure } from "./Disclosure";
import styles from "./NotificationBell.module.css";

/** The accessible name: the count when there is one, otherwise just "Notifications". */
export function bellLabel(count: number | null): string {
  if (count === null || count <= 0) return "Notifications";
  return `Notifications, ${count > 99 ? "more than 99" : count} unread`;
}

const LATEST = 5;

/**
 * The bell (plan §6): the unread count, from the one polling hook in the app (30 s while the tab
 * is visible, at once after `notifyNotificationsChanged()`), and a panel with the latest five
 * notifications grouped by source, "View all" and the notification settings. The panel is a
 * disclosure like the account menu: Tab moves into it, Escape or a click outside closes it and
 * returns focus to the bell. It asks for the latest notifications each time it opens, and only
 * then. Zero or not yet known: a plain bell, no badge.
 */
export function NotificationBell() {
  const count = useUnreadNotificationCount(true);
  const label = bellLabel(count);
  const hasUnread = count !== null && count > 0;

  return (
    <Disclosure
      className={styles.anchor}
      panelClassName={styles.panel}
      buttonClassName={styles.bell}
      label={label}
      title={label}
      button={
        <>
          <Bell size={20} aria-hidden="true" />
          {hasUnread && (
            <span className={styles.badge} aria-hidden="true">
              {count > 99 ? "99+" : count}
            </span>
          )}
        </>
      }
    >
      {/* Rendered in the same update that opens the panel, so Tab after Enter lands inside it. */}
      {(close, _current, open) => (open ? <LatestNotifications onNavigate={close} /> : null)}
    </Disclosure>
  );
}

function LatestNotifications({ onNavigate }: { onNavigate: () => void }) {
  const latest = useApiResource("notifications:latest", (signal) => fetchNotifications({ limit: LATEST }, undefined, signal));
  // Reopened before the last answer was released: ask again, so an opening always shows the latest.
  const { retry } = latest;
  const openedWith = useRef(latest.status);
  useEffect(() => {
    if (openedWith.current === "success" || openedWith.current === "empty") retry();
  }, [retry]);
  const data = latest.data;
  const groups = data ? groupBySource(data.notifications) : [];

  return (
    <div className={styles.content}>
      <div className={styles.head}>
        <h2 className={styles.heading}>Notifications</h2>
        {data && <p className={styles.summary}>{data.unread_count > 0 ? `${data.unread_count} unread` : "Nothing unread"}</p>}
      </div>

      {latest.status === "loading" || latest.status === "idle" ? (
        <p className={styles.state} role="status">
          Loading the latest notifications…
        </p>
      ) : latest.status === "error" ? (
        <div className={styles.state}>
          <p className={styles.stateText}>The latest notifications could not be loaded.</p>
          <button type="button" className={styles.retry} onClick={latest.retry}>
            Try again
          </button>
        </div>
      ) : groups.length === 0 ? (
        <p className={styles.state}>No notifications yet.</p>
      ) : (
        groups.map((group) => (
          <section key={group.key} className={styles.group} aria-label={group.label}>
            <h3 className={styles.groupTitle}>{group.label}</h3>
            <ul className={styles.list}>
              {group.items.map((item) => {
                const href = notificationHref(item);
                const unread = !item.read_at;
                const time = notificationTime(item.created_at);
                return (
                  <li key={item.id} className={`${styles.item} ${unread ? styles.unread : ""}`}>
                    {href ? (
                      <Link href={href} className={styles.title} onClick={onNavigate}>
                        {item.title}
                      </Link>
                    ) : (
                      <span className={styles.title}>{item.title}</span>
                    )}
                    <span className={styles.meta}>
                      {time && <time dateTime={item.created_at}>{time}</time>}
                      {unread && (
                        <span className={styles.unreadMark}>
                          <span className={styles.dot} aria-hidden="true" />
                          Unread
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}

      <div className={styles.footer}>
        <Link href={NOTIFICATIONS_HREF} className={styles.footerLink} onClick={onNavigate}>
          View all notifications
        </Link>
        <Link href="/settings#notifications" className={styles.footerLink} onClick={onNavigate}>
          Notification settings
        </Link>
      </div>
    </div>
  );
}
