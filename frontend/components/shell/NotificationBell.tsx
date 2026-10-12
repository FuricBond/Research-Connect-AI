"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useUnreadNotificationCount } from "../../hooks/useUnreadNotificationCount";
import { NOTIFICATIONS_HREF, isWithin } from "../../utils/navigation";
import styles from "./NotificationBell.module.css";

/** The accessible name: the count when there is one, otherwise just "Notifications". */
export function bellLabel(count: number | null): string {
  if (count === null || count <= 0) return "Notifications";
  return `Notifications, ${count > 99 ? "more than 99" : count} unread`;
}

/**
 * The one way to the notifications, and the one place the unread count is shown. Rendered
 * once, in the header, for a signed-in account only; the count comes from the existing
 * polling hook (30 s while the tab is visible, at once after `notifyNotificationsChanged()`),
 * so the app asks for it from one place. Zero or not yet known: a plain bell, no badge.
 */
export function NotificationBell() {
  const pathname = usePathname() ?? "/";
  const count = useUnreadNotificationCount(true);
  const label = bellLabel(count);
  const hasUnread = count !== null && count > 0;

  return (
    <Link
      href={NOTIFICATIONS_HREF}
      className={styles.bell}
      aria-label={label}
      title={label}
      aria-current={isWithin(pathname, NOTIFICATIONS_HREF) ? "page" : undefined}
    >
      <Bell size={20} aria-hidden="true" />
      {hasUnread && (
        <span className={styles.badge} aria-hidden="true">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
