"use client";

import Link from "next/link";
import { useLatestNotifications } from "../../hooks/useUnreadNotificationCount";
import { notificationHref, notificationTime } from "../../utils/notifications";
import { DashboardModule, ModuleLoading } from "./Module";
import styles from "./Dashboard.module.css";

/**
 * "Notifications" (plan §8, audit FUNC-11): the unread count and the latest three, read from the
 * bell's own request, so this module adds none to the dashboard's budget.
 */
export function LatestNotifications() {
  const answer = useLatestNotifications();
  return (
    <DashboardModule id="dashboard-notifications" title="Notifications" action={<Link href="/notifications">All notifications</Link>} reserve="counts">
      {answer === null ? (
        <ModuleLoading label="Loading your notifications" />
      ) : answer.failed ? (
        <p className={styles.quiet}>Your notifications could not be loaded just now. They will appear here when they can.</p>
      ) : answer.items.length === 0 ? (
        <p className={styles.quiet}>Nothing new. Deadline reminders and updates about your work appear here.</p>
      ) : (
        <>
          <p className={styles.quiet}>{answer.unread === 0 ? "All read." : `${answer.unread} unread.`}</p>
          <ul className={styles.list}>
            {answer.items.map((item) => {
              const href = notificationHref(item);
              const time = notificationTime(item.created_at);
              return (
                <li key={item.id} className={styles.item}>
                  {href ? (
                    <Link href={href} className={styles.itemTitle}>
                      {item.title}
                    </Link>
                  ) : (
                    <span className={styles.itemTitle}>{item.title}</span>
                  )}
                  {time && <div className={styles.meta}>{time}</div>}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </DashboardModule>
  );
}
