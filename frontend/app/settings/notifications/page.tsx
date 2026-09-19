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
import { DiscoveryNavbar } from "@/components/discovery/DiscoveryNavbar";
import {
  fetchNotificationPreferences,
  updateNotificationPreferences,
  fetchReminderRules,
  createReminderRule,
  deleteReminderRule,
} from "@/services/api";
import {
  NotificationPreference,
  ReminderRule,
  DeliveryChannel,
  OffsetUnit,
} from "@/types/notification";
import "@/styles/notifications.css";

export default function NotificationSettingsPage() {
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
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
    try {
      await deleteReminderRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (err: any) {
      console.error("Failed to delete reminder rule:", err);
    }
  };

  return (
    <div className="discovery-container">
      <DiscoveryNavbar />

      <main className="preferences-container">
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
                  checked={preferences?.in_app_enabled ?? true}
                  onChange={() => handleTogglePreference("in_app_enabled")}
                />
                <span className="slider" />
              </label>
            </div>

            <div className="preference-toggle-item">
              <div className="preference-toggle-info">
                <h4>Email Alerts</h4>
                <p>Send digest emails with canonical deadline timestamps and venue details.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
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
                  checked={preferences?.calendar_event_reminders_enabled ?? true}
                  onChange={() => handleTogglePreference("calendar_event_reminders_enabled")}
                />
                <span className="slider" />
              </label>
            </div>
          </div>
        </div>

        {/* Section 3: Reminder Schedule Rules */}
        <div className="preferences-section">
          <h2 className="preferences-section-title">Configured Reminder Schedules</h2>
          <p className="preferences-section-desc">
            Define exact time offsets for advance deadline reminders (e.g. 14 days, 3 days, 24 hours).
          </p>

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
                      {rule.delivery_channel}
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

          {/* Add Rule Form */}
          <form className="rule-add-form" onSubmit={handleAddRule}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Remind me</span>
              <input
                type="number"
                min="1"
                max="365"
                value={newOffsetAmount}
                onChange={(e) => setNewOffsetAmount(Number(e.target.value))}
                className="notifications-select"
                style={{ width: 70 }}
                required
              />
              <select
                className="notifications-select"
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
                value={newChannel}
                onChange={(e) => setNewChannel(e.target.value as DeliveryChannel)}
              >
                <option value="IN_APP">In-App</option>
                <option value="EMAIL">Email</option>
                <option value="PUSH">Push</option>
              </select>
            </div>

            <button type="submit" className="notifications-btn-primary">
              <Plus size={14} />
              <span>Add Schedule</span>
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
