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
  Filter,
  Settings,
  RefreshCw,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { DiscoveryNavbar } from "@/components/discovery/DiscoveryNavbar";
import {
  fetchNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  triggerReminderScheduler,
} from "@/services/api";
import { NotificationItem, NotificationType } from "@/types/notification";
import "@/styles/notifications.css";
import { RequireAuth } from "../../components/auth/RequireAuth";

function NotificationsPage() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"all" | "unread">("all");
  const [selectedType, setSelectedType] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const loadNotifications = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchNotifications({
        unreadOnly: activeTab === "unread",
        notificationType: selectedType ? (selectedType as NotificationType) : undefined,
      });
      setNotifications(res.notifications);
      setUnreadCount(res.unread_count);
      setTotalCount(res.total);
    } catch (err: any) {
      setError(err?.message || "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [activeTab, selectedType]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  const handleMarkAsRead = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await markNotificationAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
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
    } catch (err: any) {
      console.error("Failed to mark all as read:", err);
    }
  };

  const handleTriggerScheduler = async () => {
    try {
      setIsRefreshing(true);
      await triggerReminderScheduler();
      await loadNotifications();
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
              <span className="notifications-stat-value">In-App, Email</span>
            </div>
            <div className="notifications-stat-card">
              <span className="notifications-stat-label">Scheduler Status</span>
              <span className="notifications-stat-value highlight">Active</span>
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
              onClick={loadNotifications}
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

              return (
                <div
                  key={notif.id}
                  className={`notification-card ${isUnread ? "unread" : ""}`}
                >
                  <div
                    className={`notification-icon-wrap ${notif.notification_type}`}
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
