"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  Bell,
  BellRing,
  Check,
  CheckCheck,
  Clock,
  AlertTriangle,
  Calendar,
  CalendarDays,
  ExternalLink,
  FileText,
  Filter,
  Settings,
  RefreshCw,
  Sparkles,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  UserCheck,
  UserCog,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import { DiscoveryNavbar } from "@/components/discovery/DiscoveryNavbar";
import {
  fetchNotificationDeliveryStatus,
  fetchNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  triggerReminderScheduler,
} from "@/services/api";
import {
  NotificationDeliveryStatus,
  NotificationItem,
  NotificationType,
} from "@/types/notification";
import "@/styles/notifications.css";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { useSession } from "../../components/auth/SessionProvider";
import { UNREAD_POLL_MS, notifyNotificationsChanged } from "../../hooks/useUnreadNotificationCount";

/** Phase 5.16: the channels that actually reach this user, e.g. "In-App, Email". */
function describeChannels(status: NotificationDeliveryStatus | null): string {
  if (status === null) return "—";
  const channels: string[] = [];
  if (status.in_app_enabled) channels.push("In-App");
  if (status.email_enabled && status.email_delivery_available) channels.push("Email");
  return channels.length > 0 ? channels.join(", ") : "None";
}

/** Workspace collaboration notifications, named for their icon's accessible label. */
const COLLABORATION_LABELS: Partial<Record<NotificationType, string>> = {
  WORKSPACE_INVITATION: "Workspace invitation",
  INVITATION_ACCEPTED: "Invitation accepted",
  MEMBER_ROLE_CHANGED: "Role changed",
  MEMBER_REMOVED: "Removed from workspace",
  TASK_ASSIGNED: "Task assigned",
  TASK_COMPLETED: "Task completed",
  DOCUMENT_UPDATED: "Document updated",
  COLLABORATION_ACTIVITY: "Workspace activity",
};

function describeReminders(status: NotificationDeliveryStatus | null): string {
  if (status === null) return "—";
  if (!status.reminders_scheduled || status.reminder_interval_seconds === null) return "Manual only";
  return `Every ${Math.max(1, Math.round(status.reminder_interval_seconds / 60))} min`;
}

function NotificationsPage() {
  const { hasRole } = useSession();
  const isAdmin = hasRole("ADMIN");
  const [deliveryStatus, setDeliveryStatus] = useState<NotificationDeliveryStatus | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"all" | "unread">("all");
  const [selectedType, setSelectedType] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // A quiet refresh (Phase 5.16 polling) keeps the list on screen and ignores failures.
  const loadNotifications = useCallback(async (quiet = false) => {
    try {
      if (!quiet) {
        setLoading(true);
        setError(null);
      }
      const res = await fetchNotifications({
        unreadOnly: activeTab === "unread",
        notificationType: selectedType ? (selectedType as NotificationType) : undefined,
      });
      setNotifications(res.notifications);
      setUnreadCount(res.unread_count);
      setTotalCount(res.total);
    } catch (err: any) {
      if (!quiet) setError(err?.message || "Failed to load notifications.");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [activeTab, selectedType]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  // Phase 5.16: new notifications appear without a reload while the tab is visible.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadNotifications(true);
    }, UNREAD_POLL_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void loadNotifications(true);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [loadNotifications]);

  useEffect(() => {
    const controller = new AbortController();
    fetchNotificationDeliveryStatus(controller.signal)
      .then(setDeliveryStatus)
      .catch(() => {
        // The header then shows "—"; the notifications themselves still load.
      });
    return () => controller.abort();
  }, []);

  const handleMarkAsRead = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await markNotificationAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      notifyNotificationsChanged();
    } catch (err: any) {
      console.error("Failed to mark as read:", err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsAsRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
      notifyNotificationsChanged();
    } catch (err: any) {
      console.error("Failed to mark all as read:", err);
    }
  };

  const handleTriggerScheduler = async () => {
    try {
      setIsRefreshing(true);
      await triggerReminderScheduler();
      await loadNotifications();
      notifyNotificationsChanged();
    } catch (err: any) {
      console.error("Scheduler trigger failed:", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  const formatTimestamp = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoStr;
    }
  };

  const getNotificationIcon = (type: NotificationType) => {
    switch (type) {
      case "DEADLINE_TODAY":
        return <AlertTriangle size={18} />;
      case "DEADLINE_UPCOMING":
        return <Clock size={18} />;
      case "DEADLINE_EXTENDED":
        return <Sparkles size={18} />;
      case "DEADLINE_MOVED_EARLIER":
        return <Clock size={18} />;
      case "DEADLINE_CONFLICT":
        return <AlertTriangle size={18} />;
      case "CALENDAR_EVENT_UPCOMING":
        return <CalendarDays size={18} />;
      case "WORKSPACE_INVITATION":
        return <UserPlus size={18} />;
      case "INVITATION_ACCEPTED":
        return <UserCheck size={18} />;
      case "MEMBER_ROLE_CHANGED":
        return <UserCog size={18} />;
      case "MEMBER_REMOVED":
        return <UserMinus size={18} />;
      case "TASK_ASSIGNED":
        return <ClipboardList size={18} />;
      case "TASK_COMPLETED":
        return <ClipboardCheck size={18} />;
      case "DOCUMENT_UPDATED":
        return <FileText size={18} />;
      case "COLLABORATION_ACTIVITY":
        return <Users size={18} />;
      default:
        return <Bell size={18} />;
    }
  };

  return (
    <div className="discovery-container">
      <DiscoveryNavbar />

      <main className="notifications-container">
        {/* Header */}
        <div className="notifications-header">
          <div className="notifications-header-top">
            <div className="notifications-title-wrap">
              <h1>Notification Center</h1>
              <p className="notifications-tagline">
                Phase 4.5 Deadline Reminders, Scheduled Alerts & In-App Intelligence
              </p>
            </div>
            <div className="notifications-actions-bar">
              {/* The reminder pass is an administrator action (the API answers 403 to others). */}
              {isAdmin && (
                <button
                  type="button"
                  className="notifications-btn-secondary"
                  onClick={handleTriggerScheduler}
                  disabled={isRefreshing}
                  title="Run background reminder evaluation"
                >
                  <RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
                  <span>Evaluate Now</span>
                </button>
              )}
              <Link
                href="/settings/notifications"
                className="notifications-btn-secondary"
              >
                <Settings size={14} />
                <span>Preferences</span>
              </Link>
              {unreadCount > 0 && (
                <button
                  type="button"
                  className="notifications-btn-primary"
                  onClick={handleMarkAllRead}
                >
                  <CheckCheck size={14} />
                  <span>Mark All Read</span>
                </button>
              )}
            </div>
          </div>

          {/* Stats Strip */}
          <div className="notifications-stats-strip">
            <div className="notifications-stat-card">
              <span className="notifications-stat-label">Unread Alerts</span>
              <span
                className={`notifications-stat-value ${
                  unreadCount > 0 ? "highlight" : ""
                }`}
              >
                {unreadCount}
              </span>
            </div>
            <div className="notifications-stat-card">
              <span className="notifications-stat-label">Total Notifications</span>
              <span className="notifications-stat-value">{totalCount}</span>
            </div>
            <div className="notifications-stat-card">
              <span className="notifications-stat-label">Active Channels</span>
              <span className="notifications-stat-value">{describeChannels(deliveryStatus)}</span>
            </div>
            <div className="notifications-stat-card">
              <span className="notifications-stat-label">Deadline Reminders</span>
              <span
                className={`notifications-stat-value ${
                  deliveryStatus?.reminders_scheduled ? "highlight" : ""
                }`}
              >
                {describeReminders(deliveryStatus)}
              </span>
            </div>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="notifications-filter-bar">
          <div className="notifications-tabs">
            <button
              type="button"
              className={`notifications-tab ${activeTab === "all" ? "active" : ""}`}
              onClick={() => setActiveTab("all")}
            >
              <span>All Alerts</span>
              <span className="notifications-tab-badge">{totalCount}</span>
            </button>
            <button
              type="button"
              className={`notifications-tab ${activeTab === "unread" ? "active" : ""}`}
              onClick={() => setActiveTab("unread")}
            >
              <span>Unread</span>
              {unreadCount > 0 && (
                <span className="notifications-tab-badge">{unreadCount}</span>
              )}
            </button>
          </div>

          <div className="notifications-type-filter">
            <Filter size={14} color="var(--text-muted)" />
            <select
              aria-label="Filter by notification type"
              className="notifications-select"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
            >
              <option value="">All Types</option>
              <option value="DEADLINE_UPCOMING">Upcoming Deadline</option>
              <option value="DEADLINE_TODAY">Due Today</option>
              <option value="DEADLINE_EXTENDED">Deadline Extended</option>
              <option value="DEADLINE_MOVED_EARLIER">Moved Earlier</option>
              <option value="DEADLINE_CONFLICT">Deadline Conflict</option>
              <option value="CALENDAR_EVENT_UPCOMING">Calendar Event</option>
              <option value="SUBMISSION_STATUS_CHANGE">Submission Status</option>
              <option value="SYSTEM">System</option>
              <option value="POSTING_MATCH">Posting Match</option>
            </select>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="notifications-loading">
            <div className="notification-skeleton" />
            <div className="notification-skeleton" />
            <div className="notification-skeleton" />
          </div>
        ) : error ? (
          <div className="notifications-empty">
            <AlertTriangle size={32} color="#ef4444" />
            <h3>Unable to Load Notifications</h3>
            <p>{error}</p>
            <button
              type="button"
              className="notifications-btn-secondary"
              style={{ marginTop: 16 }}
              onClick={() => loadNotifications()}
            >
              Retry
            </button>
          </div>
        ) : notifications.length === 0 ? (
          <div className="notifications-empty">
            <BellRing size={36} color="var(--text-muted)" />
            <h3>No notifications found</h3>
            <p>
              {activeTab === "unread"
                ? "You're all caught up! No unread deadline reminders."
                : "You have no notifications yet. Reminders will appear as canonical deadlines approach."}
            </p>
          </div>
        ) : (
          <div className="notifications-list">
            {notifications.map((notif) => {
              const isUnread = !notif.read_at;
              const meta = notif.metadata_json || {};
              const typeLabel = COLLABORATION_LABELS[notif.notification_type];

              return (
                <div
                  key={notif.id}
                  className={`notification-card ${isUnread ? "unread" : ""}`}
                >
                  <div
                    className={`notification-icon-wrap ${notif.notification_type}`}
                    role={typeLabel ? "img" : undefined}
                    aria-label={typeLabel}
                    title={typeLabel}
                  >
                    {getNotificationIcon(notif.notification_type)}
                  </div>

                  <div className="notification-content">
                    <div className="notification-content-header">
                      <h3 className="notification-title">{notif.title}</h3>
                      <span className="notification-time">
                        {formatTimestamp(notif.created_at)}
                      </span>
                    </div>

                    <p className="notification-body">{notif.body}</p>

                    <div className="notification-tags">
                      <span className="notification-pill channel">
                        {notif.delivery_channel}
                      </span>
                      <span
                        className={`notification-pill status-${notif.delivery_status.toLowerCase()}`}
                      >
                        {notif.delivery_status}
                      </span>
                      {notif.email_status === "SENT" && (
                        <span className="notification-pill channel">Emailed</span>
                      )}
                      {notif.deadline_type && (
                        <span className="notification-pill channel">
                          {notif.deadline_type.replace("_", " ")}
                        </span>
                      )}
                      {meta.canonical_deadline && (
                        <span className="notification-pill channel">
                          Due: {meta.canonical_deadline.split("T")[0]}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="notification-actions">
                    {notif.opportunity_id && (
                      <Link
                        href={`/workspace`}
                        className="notification-btn-icon"
                        title="View in Workspace"
                      >
                        <ExternalLink size={15} />
                      </Link>
                    )}
                    {notif.calendar_event_id && (
                      <Link
                        href={`/calendar`}
                        className="notification-btn-icon"
                        title="View in Calendar"
                      >
                        <Calendar size={15} />
                      </Link>
                    )}
                    {notif.source_type === "WORKSPACE" && notif.source_id && (
                      <Link
                        href={`/workspace/${notif.source_id}`}
                        className="notification-btn-icon"
                        title="Open workspace"
                        aria-label="Open workspace"
                      >
                        <ExternalLink size={15} />
                      </Link>
                    )}
                    {notif.source_type === "RESEARCH_POSTING" && notif.source_id && (
                      <Link
                        href={`/postings/${notif.source_id}`}
                        className="notification-btn-icon"
                        title="View posting"
                        aria-label="View posting"
                      >
                        <ExternalLink size={15} />
                      </Link>
                    )}
                    {isUnread && (
                      <button
                        type="button"
                        className="notification-btn-icon"
                        onClick={(e) => handleMarkAsRead(notif.id, e)}
                        title="Mark as Read"
                      >
                        <Check size={15} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}


export default function NotificationsPageRoute() {
  return (
    <RequireAuth>
      <NotificationsPage  />
    </RequireAuth>
  );
}
