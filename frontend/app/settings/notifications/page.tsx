"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  Bell,
  Mail,
  Clock,
  ArrowLeft,
  Plus,
  Trash2,
  Check,
  AlertCircle,
  ShieldCheck,
  Save,
} from "lucide-react";
import {
  changePassword,
  fetchNotificationDeliveryStatus,
  fetchNotificationPreferences,
  updateNotificationPreferences,
  fetchReminderRules,
  createReminderRule,
  deleteReminderRule,
} from "@/services/api";
import { storeSession } from "@/services/auth";
import {
  NotificationDeliveryStatus,
  NotificationPreference,
  ReminderRule,
  DeliveryChannel,
  OffsetUnit,
} from "@/types/notification";
import "@/styles/notifications.css";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { useSession } from "../../../components/auth/SessionProvider";

// Phase 5.15: the fit a new posting needs before a student is alerted about it.
const POSTING_MATCH_THRESHOLDS = [40, 60, 80];

function NotificationSettingsPage() {
  // Posting match alerts are sent to student accounts only, so only students see the switch.
  const { hasRole } = useSession();
  const isStudent = hasRole("STUDENT");
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  // Phase 5.16: whether this server emails notifications at all.
  const [deliveryStatus, setDeliveryStatus] = useState<NotificationDeliveryStatus | null>(null);
  const [rules, setRules] = useState<ReminderRule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // New rule form state
  const [newOffsetAmount, setNewOffsetAmount] = useState<number>(7);
  const [newOffsetUnit, setNewOffsetUnit] = useState<OffsetUnit>("DAYS");
  const [newChannel, setNewChannel] = useState<DeliveryChannel>("IN_APP");
  const [newEventType, setNewEventType] = useState<string>("");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [prefsRes, rulesRes] = await Promise.all([
        fetchNotificationPreferences(),
        fetchReminderRules(),
      ]);
      setPreferences(prefsRes);
      setRules(rulesRes.rules);
    } catch (err: any) {
      setError(err?.message || "Failed to load notification settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const controller = new AbortController();
    fetchNotificationDeliveryStatus(controller.signal)
      .then(setDeliveryStatus)
      .catch(() => {
        // Without it the page simply shows no note; the settings still work.
      });
    return () => controller.abort();
  }, []);

  const handleTogglePreference = async (key: keyof NotificationPreference) => {
    if (!preferences) return;
    const updatedVal = !preferences[key];
    const newPrefs = { ...preferences, [key]: updatedVal };
    setPreferences(newPrefs);

    try {
      setSaving(true);
      await updateNotificationPreferences({ [key]: updatedVal });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err: any) {
      console.error("Failed to update preferences:", err);
      // Revert
      setPreferences(preferences);
    } finally {
      setSaving(false);
    }
  };

  const handleThresholdChange = async (minScore: number) => {
    if (!preferences) return;
    const previous = preferences;
    setPreferences({ ...preferences, posting_match_min_score: minScore });

    try {
      setSaving(true);
      await updateNotificationPreferences({ posting_match_min_score: minScore });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err: any) {
      console.error("Failed to update the posting match threshold:", err);
      setPreferences(previous);
    } finally {
      setSaving(false);
    }
  };

  // Phase 6.7: changing the password revokes every token, so this browser keeps the new one.
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordChanged, setPasswordChanged] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordChanged(false);
    if (newPassword !== confirmPassword) {
      setPasswordError("The new passwords do not match.");
      return;
    }
    setChangingPassword(true);
    try {
      const response = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      storeSession(response);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordChanged(true);
    } catch (err: any) {
      setPasswordError(err?.detail || err?.message || "Failed to change the password.");
    } finally {
      setChangingPassword(false);
    }
  };

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await createReminderRule({
        offset_amount: Number(newOffsetAmount),
        offset_unit: newOffsetUnit,
        delivery_channel: newChannel,
        event_type: newEventType || undefined,
        is_active: true,
      });
      setRules((prev) => [...prev, created]);
      // Reset form to defaults
      setNewOffsetAmount(3);
    } catch (err: any) {
      console.error("Failed to add reminder rule:", err);
      alert("Failed to add reminder rule. A duplicate rule may already exist.");
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    setError(null);
    try {
      await deleteReminderRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (err: any) {
      console.error("Failed to delete reminder rule:", err);
      // The rule stays listed because it was not deleted. A 401 has already been reported
      // to the session by the API client; this only tells the person the delete failed.
      setError(err?.message || "Failed to delete reminder rule.");
    }
  };

  return (
    <div className="discovery-container">
      <div className="preferences-container">
        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <Link
            href="/notifications"
            className="notifications-btn-secondary"
            style={{ marginBottom: 16 }}
          >
            <ArrowLeft size={14} />
            <span>Back to Notifications</span>
          </Link>
          <h1 style={{ fontSize: 26, fontWeight: 700, margin: "8px 0 4px 0", color: "var(--text-main)" }}>
            Notification & Reminder Preferences
          </h1>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 14 }}>
            Configure delivery channels, scheduled reminder timings, and deadline intelligence alerts.
          </p>
        </div>

        {saveSuccess && (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid #10b981",
              borderRadius: "var(--radius-md)",
              color: "#059669",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 20,
            }}
          >
            <Check size={16} />
            <span>Preferences saved successfully.</span>
          </div>
        )}

        {error && (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid #ef4444",
              borderRadius: "var(--radius-md)",
              color: "#dc2626",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 20,
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Section 1: Delivery Channels */}
        <div className="preferences-section">
          <h2 className="preferences-section-title">Delivery Channels</h2>
          <p className="preferences-section-desc">
            Choose where you receive deadline alerts and research updates.
          </p>

          <div className="preference-toggle-list">
            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>In-App Notifications</h4>
                <p>Receive notifications in the ResearchConnect Notification Center and navigation badge.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="In-App Notifications"
                  checked={preferences?.in_app_enabled ?? true}
                  onChange={() => handleTogglePreference("in_app_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4 id="email-alerts-label">Email Alerts</h4>
                <p>
                  Email a copy of important notifications, such as deadline reminders,
                  application updates and posting matches.
                </p>
                {deliveryStatus !== null && !deliveryStatus.email_delivery_available && (
                  <p className="preference-toggle-note" role="note">
                    Email isn&apos;t set up on this server yet, so alerts appear in the app only.
                  </p>
                )}
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-labelledby="email-alerts-label"
                  checked={preferences?.email_enabled ?? true}
                  onChange={() => handleTogglePreference("email_enabled")}
                />
                <span className="slider" />
              </label>
            </div>
          </div>
        </div>

        {/* Section 2: Alert Categories */}
        <div className="preferences-section">
          <h2 className="preferences-section-title">Alert Categories</h2>
          <p className="preferences-section-desc">
            Fine-tune which types of events trigger notifications.
          </p>

          <div className="preference-toggle-list">
            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>Upcoming Deadline Reminders</h4>
                <p>Scheduled advance reminders before canonical submission and milestone deadlines.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="Upcoming Deadline Reminders"
                  checked={preferences?.deadline_reminders_enabled ?? true}
                  onChange={() => handleTogglePreference("deadline_reminders_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>Deadline Extensions</h4>
                <p>Notify when an authoritative source announces a deadline extension.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="Deadline Extensions"
                  checked={preferences?.extension_notifications_enabled ?? true}
                  onChange={() => handleTogglePreference("extension_notifications_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>Deadline Conflicts</h4>
                <p>Alert when conflicting dates are reported by multiple equal-authority sources.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="Deadline Conflicts"
                  checked={preferences?.conflict_notifications_enabled ?? true}
                  onChange={() => handleTogglePreference("conflict_notifications_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>Calendar Planning Events</h4>
                <p>Reminders for custom milestones and planning sessions created in your Research Calendar.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  aria-label="Calendar Planning Events"
                  checked={preferences?.calendar_event_reminders_enabled ?? true}
                  onChange={() => handleTogglePreference("calendar_event_reminders_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            {isStudent && (
              <div className="preference-toggle-item">
                <div className="preference-toggle-info">
                  <h4 id="posting-match-label">Notify me when a new posting matches my interests</h4>
                  <p>
                    When faculty publish a new research posting that fits your interests at least
                    this well, you get one in-app alert.
                  </p>
                  <select
                    className="notifications-select"
                    aria-label="Minimum fit for posting alerts"
                    value={preferences?.posting_match_min_score ?? 60}
                    disabled={!preferences?.posting_match_alerts_enabled || saving}
                    onChange={(e) => handleThresholdChange(Number(e.target.value))}
                  >
                    {POSTING_MATCH_THRESHOLDS.map((threshold) => (
                      <option key={threshold} value={threshold}>
                        {threshold}% fit or better
                      </option>
                    ))}
                  </select>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    aria-labelledby="posting-match-label"
                    checked={preferences?.posting_match_alerts_enabled ?? false}
                    onChange={() => handleTogglePreference("posting_match_alerts_enabled")}
                  />
                  <span className="slider" />
                </label>
              </div>
            )}
          </div>
        </div>

        {/* Section 3: Reminder Schedule Rules */}
        <div className="preferences-section">
          <h2 className="preferences-section-title">Configured Reminder Schedules</h2>
          <p className="preferences-section-desc">
            Define exact time offsets for advance deadline reminders (e.g. 14 days, 3 days, 24 hours).
          </p>

          <div className="rules-table-scroll" role="region" aria-label="Configured reminder schedules" tabIndex={0}>
            <table className="rules-table">
              <thead>
                <tr>
                  <th>Offset</th>
                  <th>Channel</th>
                  <th>Target Milestone</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.id}>
                    <td style={{ fontWeight: 600 }}>
                      {rule.offset_amount} {rule.offset_unit.toLowerCase()} before
                    </td>
                    <td>
                      <span className="notification-pill channel">
                        {/* Push delivery does not exist yet; older rules may still name it. */}
                        {rule.delivery_channel === "PUSH" ? "Push (not available yet)" : rule.delivery_channel}
                      </span>
                    </td>
                    <td>
                      {rule.event_type ? rule.event_type.replace("_", " ") : "All Milestones"}
                    </td>
                    <td>
                      <span
                        style={{
                          color: rule.is_active ? "#059669" : "var(--text-muted)",
                          fontSize: 12,
                          fontWeight: 600,
                        }}
                      >
                        {rule.is_active ? "Active" : "Paused"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="notification-btn-icon"
                        onClick={() => handleDeleteRule(rule.id)}
                        title="Delete Rule"
                      >
                        <Trash2 size={14} color="#ef4444" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Add Rule Form */}
          <form className="rule-add-form" onSubmit={handleAddRule}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Remind me</span>
              <input
                type="number"
                min="1"
                max="365"
                aria-label="Reminder amount"
                value={newOffsetAmount}
                onChange={(e) => setNewOffsetAmount(Number(e.target.value))}
                className="notifications-select"
                style={{ width: 70 }}
                required
              />
              <select
                className="notifications-select"
                aria-label="Reminder unit"
                value={newOffsetUnit}
                onChange={(e) => setNewOffsetUnit(e.target.value as OffsetUnit)}
              >
                <option value="DAYS">Days</option>
                <option value="HOURS">Hours</option>
                <option value="MINUTES">Minutes</option>
              </select>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>before via</span>
              <select
                className="notifications-select"
                aria-label="Reminder channel"
                value={newChannel}
                onChange={(e) => setNewChannel(e.target.value as DeliveryChannel)}
              >
                <option value="IN_APP">In-App</option>
                <option value="EMAIL">Email</option>
              </select>
            </div>

            <button type="submit" className="notifications-btn-primary">
              <Plus size={14} />
              <span>Add Schedule</span>
            </button>
          </form>
        </div>

        {/* Section: Account security (Phase 6.7) */}
        <div className="preferences-section">
          <h2 className="preferences-section-title">Change Password</h2>
          <p className="preferences-section-desc">
            Changing your password signs you out on every other device. This browser stays signed in.
          </p>

          <form
            onSubmit={handleChangePassword}
            aria-label="Change password"
            style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 360 }}
          >
            <label htmlFor="current-password" style={{ fontSize: 13, fontWeight: 600 }}>
              Current password
            </label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="notifications-select"
            />
            <label htmlFor="new-password" style={{ fontSize: 13, fontWeight: 600 }}>
              New password (at least 8 characters)
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="notifications-select"
            />
            <label htmlFor="confirm-password" style={{ fontSize: 13, fontWeight: 600 }}>
              Confirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="notifications-select"
            />
            {passwordError && (
              <p role="alert" style={{ margin: 0, color: "#ef4444", fontSize: 13 }}>
                {passwordError}
              </p>
            )}
            {passwordChanged && (
              <p role="status" style={{ margin: 0, color: "#059669", fontSize: 13 }}>
                Password changed. Your other sessions have been signed out.
              </p>
            )}
            <button
              type="submit"
              className="notifications-btn-primary"
              disabled={changingPassword}
              style={{ alignSelf: "flex-start" }}
            >
              <span>{changingPassword ? "Changing…" : "Change password"}</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}


export default function NotificationSettingsPageRoute() {
  return (
    <RequireAuth>
      <NotificationSettingsPage  />
    </RequireAuth>
  );
}
