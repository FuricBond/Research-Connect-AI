"use client";

import { lazy, Suspense } from "react";
import { Bell } from "lucide-react";
import { useUnreadNotificationCount } from "../../hooks/useUnreadNotificationCount";
import { Disclosure } from "./Disclosure";
import styles from "./NotificationBell.module.css";

const loadPanel = () => import("./NotificationsPanel");
const LatestNotifications = lazy(() => loadPanel().then((module) => ({ default: module.LatestNotifications })));

/** The accessible name: the count when there is one, otherwise just "Notifications". */
export function bellLabel(count: number | null): string {
  if (count === null || count <= 0) return "Notifications";
  return `Notifications, ${count > 99 ? "more than 99" : count} unread`;
}


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
      onPrepare={loadPanel}
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
      {(close, _current, open) =>
        open ? (
          <Suspense fallback={<p className={styles.state}>Loading the latest notifications…</p>}>
            <LatestNotifications onNavigate={close} />
          </Suspense>
        ) : null
      }
    </Disclosure>
  );
}
