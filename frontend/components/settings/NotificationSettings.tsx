"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useApiResource, type ApiResource } from "../../hooks/useApiResource";
import {
  createReminderRule,
  deleteReminderRule,
  fetchNotificationDeliveryStatus,
  fetchNotificationPreferences,
  fetchReminderRules,
  updateNotificationPreferences,
} from "../../services/api";
import type { DeliveryChannel, NotificationDeliveryStatus, NotificationPreference, NotificationPreferenceUpdate, OffsetUnit, ReminderRule, ReminderRuleListResponse } from "../../types/notification";
import { humanizeEnum } from "../../utils/date";
import { deliveryChannelLabel } from "../../utils/notifications";
import { useSession } from "../auth/SessionProvider";
import { Button, IconButton } from "../ui/Button/Button";
import { Select, Switch, TextInput } from "../ui/Field/Field";
import { Alert, ErrorState, SkeletonList } from "../ui/State/State";
import { actionError } from "../workspace/workflow";
import styles from "./SettingsPage.module.css";

type BooleanKey = {
  [K in keyof NotificationPreference]: NotificationPreference[K] extends boolean ? K : never;
}[keyof NotificationPreference];

const SWITCHES: { key: BooleanKey; label: string; description: string }[] = [
  { key: "in_app_enabled", label: "In-app notifications", description: "Notifications here and the count on the bell." },
  { key: "email_enabled", label: "Email alerts", description: "A copy of important notifications by email: deadline reminders, application updates and posting matches." },
  { key: "deadline_reminders_enabled", label: "Upcoming deadline reminders", description: "Reminders before the submission and milestone deadlines of the calls you track." },
  { key: "extension_notifications_enabled", label: "Deadline extensions", description: "When an authoritative source announces that a deadline was extended." },
  { key: "conflict_notifications_enabled", label: "Deadline conflicts", description: "When equally authoritative sources give different dates." },
  { key: "calendar_event_reminders_enabled", label: "Calendar planning events", description: "Reminders for the milestones you add to your calendar." },
];

/** Phase 5.15: the fit a new posting needs before a student is alerted about it. */
const POSTING_MATCH_THRESHOLDS = [40, 60, 80];
const CHANNELS: DeliveryChannel[] = ["IN_APP", "EMAIL"]; // push delivery does not exist
const UNITS: { value: OffsetUnit; label: string }[] = [
  { value: "DAYS", label: "Days" },
  { value: "HOURS", label: "Hours" },
  { value: "MINUTES", label: "Minutes" },
];

function channelsInUse(status: NotificationDeliveryStatus): string {
  const email = status.email_enabled && status.email_delivery_available;
  if (status.in_app_enabled && email) return "In the app and by email";
  if (status.in_app_enabled) return "In the app";
  if (email) return "By email";
  return "Nowhere: both are switched off";
}

function reminderSchedule(status: NotificationDeliveryStatus): string {
  if (!status.reminders_scheduled || status.reminder_interval_seconds === null) return "Checked only when an administrator runs the check";
  const minutes = Math.max(1, Math.round(status.reminder_interval_seconds / 60));
  return `Checked every ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

function ruleOffset(rule: ReminderRule): string {
  const unit = rule.offset_unit.toLowerCase();
  return `${rule.offset_amount} ${rule.offset_amount === 1 ? unit.replace(/s$/, "") : unit} before`;
}

/**
 * P8 — Settings → Notifications: how notifications reach you (the server's delivery status), the
 * switches the API stores (each saved on its own as it changes, rolled back and explained when
 * the server refuses), the posting-match alert for students, and the reminder schedules. There is
 * no push option: push delivery does not exist (a rule saved with it says "not available yet").
 */
export function NotificationSettings() {
  const { hasRole } = useSession();
  const isStudent = hasRole("STUDENT");
  const prefs = useApiResource("notifications:preferences", (signal) => fetchNotificationPreferences(undefined, signal));
  // Asked for once the preferences have answered: both endpoints create a new account's
  // preferences on first use, and two at once collide on the server (a 500 for one of them).
  const delivery = useApiResource(prefs.data ? "notifications:delivery-status" : null, (signal) => fetchNotificationDeliveryStatus(signal));
  const rulesResource = useApiResource("notifications:reminder-rules", (signal) => fetchReminderRules(undefined, signal));

  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  const [pending, setPending] = useState<Set<string>>(() => new Set());
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (prefs.data) setPreferences(prefs.data);
  }, [prefs.data]);

  const mark = (key: string, on: boolean) =>
    setPending((current) => {
      const next = new Set(current);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  /** Saves one setting; shows it at once, keeps the server's answer, rolls back on failure. */
  const save = async <K extends keyof NotificationPreferenceUpdate>(key: K, value: NonNullable<NotificationPreferenceUpdate[K]>, done: string, failed: string) => {
    if (!preferences || pending.has(key)) return;
    const before = preferences[key as keyof NotificationPreference];
    setError(null);
    setPreferences((current) => current && { ...current, [key]: value });
    mark(key, true);
    try {
      const saved = await updateNotificationPreferences({ [key]: value } as NotificationPreferenceUpdate);
      // Only this setting comes from the answer, so another change still saving is not undone.
      setPreferences((current) => current && { ...current, [key]: saved[key as keyof NotificationPreference] });
      setMessage(done);
    } catch (err) {
      setPreferences((current) => current && { ...current, [key]: before });
      setError(actionError(err, failed));
    } finally {
      mark(key, false);
    }
  };

  const toggle = (key: BooleanKey, label: string) => {
    if (!preferences) return;
    const next = !preferences[key];
    void save(key, next, `${label}: ${next ? "on" : "off"}.`, `${label} could not be switched ${next ? "on" : "off"}; it is still ${next ? "off" : "on"}.`);
  };

  if (preferences === null) {
    if (prefs.status === "error") {
      return <ErrorState headingLevel={3} title="Your notification settings could not be loaded" kind={prefs.error?.kind === "network" ? "offline" : "failed"} onRetry={prefs.retry} />;
    }
    return <SkeletonList rows={4} lines={2} label="Loading your notification settings" />;
  }

  const status = delivery.data;

  return (
    <div className={styles.stack}>
      {status && (
        <dl className={styles.facts}>
          <div className={styles.fact}>
            <dt>Notifications reach you</dt>
            <dd>{channelsInUse(status)}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Deadline reminders</dt>
            <dd>{reminderSchedule(status)}</dd>
          </div>
        </dl>
      )}

      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}

      <div className={styles.group}>
        <h3 className={styles.subheading}>What you are told about</h3>
        {SWITCHES.map((entry) => (
          <div key={entry.key}>
            <Switch
              label={entry.label}
              description={entry.description}
              checked={Boolean(preferences[entry.key])}
              disabled={pending.has(entry.key)}
              onChange={() => toggle(entry.key, entry.label)}
            />
            {entry.key === "email_enabled" && status !== undefined && !status.email_delivery_available && (
              <p className={styles.note} role="note">
                Email isn&apos;t set up on this server yet, so alerts appear in the app only.
              </p>
            )}
          </div>
        ))}
        {isStudent && (
          <div className={styles.switchWithOption}>
            <Switch
              label="Notify me when a new posting matches my interests"
              description="When faculty publish a research posting that fits your interests at least this well, you get one alert in the app."
              checked={preferences.posting_match_alerts_enabled}
              disabled={pending.has("posting_match_alerts_enabled")}
              onChange={() => toggle("posting_match_alerts_enabled", "Posting match alerts")}
            />
            <Select
              label="Minimum fit for posting alerts"
              value={preferences.posting_match_min_score ?? 60}
              disabled={!preferences.posting_match_alerts_enabled || pending.has("posting_match_min_score") || pending.has("posting_match_alerts_enabled")}
              onChange={(event) => {
                const score = Number(event.target.value);
                void save("posting_match_min_score", score, `Posting alerts from ${score}% fit.`, `The minimum fit could not be changed to ${score}%.`);
              }}
              className={styles.threshold}
            >
              {POSTING_MATCH_THRESHOLDS.map((threshold) => (
                <option key={threshold} value={threshold}>
                  {threshold}% fit or better
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>

      <ReminderRules resource={rulesResource} />
    </div>
  );
}

function ReminderRules({ resource }: { resource: ApiResource<ReminderRuleListResponse> }) {
  const [rules, setRules] = useState<ReminderRule[] | null>(null);
  useEffect(() => {
    if (resource.data) setRules(resource.data.rules);
  }, [resource.data]);
  const [amount, setAmount] = useState("7");
  const [unit, setUnit] = useState<OffsetUnit>("DAYS");
  const [channel, setChannel] = useState<DeliveryChannel>("IN_APP");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const submitting = useRef(false);
  const amountRef = useRef<HTMLInputElement>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const value = Number(amount);
    if (!Number.isInteger(value) || value < 1 || value > 365) {
      setAmountError("Enter a whole number from 1 to 365.");
      amountRef.current?.focus();
      return;
    }
    submitting.current = true;
    setSaving(true);
    setAmountError(null);
    setError(null);
    try {
      const created = await createReminderRule({ offset_amount: value, offset_unit: unit, delivery_channel: channel, is_active: true });
      setRules((current) => [...(current ?? []), created]);
      setMessage(`Added a reminder ${ruleOffset(created)}.`);
    } catch (err) {
      // The form keeps what was chosen; a duplicate is refused by the server.
      setError(actionError(err, "The reminder could not be added; you may already have it."));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  const remove = async (rule: ReminderRule) => {
    if (deleting) return;
    setDeleting(rule.id);
    setError(null);
    try {
      await deleteReminderRule(rule.id);
      setRules((current) => current && current.filter((entry) => entry.id !== rule.id));
      setMessage(`Deleted the reminder ${ruleOffset(rule)}.`);
    } catch (err) {
      // The rule stays listed because it was not deleted.
      setError(actionError(err, "The reminder could not be deleted."));
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className={styles.group}>
      <h3 className={styles.subheading}>Reminder schedule</h3>
      <p className={styles.note}>How long before a deadline you are reminded. Each reminder applies to every call you track.</p>
      <p role="status" className="rc-visually-hidden">
        {message}
      </p>
      {error && (
        <Alert tone="danger" announce>
          {error}
        </Alert>
      )}
      {rules === null ? (
        resource.status === "error" ? (
          <ErrorState bare headingLevel={4} title="Your reminders could not be loaded" onRetry={resource.retry} />
        ) : (
          <SkeletonList rows={2} label="Loading your reminders" />
        )
      ) : rules.length === 0 ? (
        <p className={styles.note}>No reminders yet.</p>
      ) : (
        <ul className={styles.rules}>
          {rules.map((rule) => (
            <li key={rule.id} className={styles.rule}>
              <span className={styles.ruleMain}>{ruleOffset(rule)}</span>
              <span className={styles.ruleMeta}>
                {deliveryChannelLabel(rule.delivery_channel)} · {rule.event_type ? humanizeEnum(rule.event_type) : "All milestones"} · {rule.is_active ? "Active" : "Paused"}
              </span>
              <IconButton
                variant="ghost"
                size="sm"
                label={`Delete the reminder ${ruleOffset(rule)}`}
                icon={<Trash2 size={16} aria-hidden="true" />}
                loading={deleting === rule.id}
                onClick={() => void remove(rule)}
              />
            </li>
          ))}
        </ul>
      )}
      <form className={styles.ruleForm} onSubmit={(event) => void add(event)} noValidate>
        <TextInput
          ref={amountRef}
          label="Remind me"
          type="number"
          inputMode="numeric"
          min={1}
          max={365}
          value={amount}
          error={amountError}
          onChange={(event) => {
            setAmount(event.target.value);
            if (amountError) setAmountError(null);
          }}
          className={styles.amount}
        />
        <Select label="Unit" value={unit} onChange={(event) => setUnit(event.target.value as OffsetUnit)}>
          {UNITS.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label} before
            </option>
          ))}
        </Select>
        <Select label="Channel" value={channel} onChange={(event) => setChannel(event.target.value as DeliveryChannel)}>
          {CHANNELS.map((value) => (
            <option key={value} value={value}>
              {deliveryChannelLabel(value)}
            </option>
          ))}
        </Select>
        <div className={styles.formEnd}>
          <Button type="submit" variant="secondary" loading={saving} leadingIcon={<Plus size={16} aria-hidden="true" />}>
            Add reminder
          </Button>
        </div>
      </form>
    </div>
  );
}
