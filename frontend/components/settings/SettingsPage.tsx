"use client";

import { ROLE_LABELS } from "../../types/auth";
import { RequireAuth } from "../auth/RequireAuth";
import { ChangePasswordForm } from "../auth/ChangePasswordForm";
import { useSession } from "../auth/SessionProvider";
import { Card } from "../ui/Card/Card";
import { PageHeader, SectionHeader } from "../ui/PageHeader/PageHeader";
import { AppearanceSettings } from "./AppearanceSettings";
import { NotificationSettings } from "./NotificationSettings";
import styles from "./SettingsPage.module.css";

/**
 * Settings (`/settings`): P3's Account (who is signed in, and the password change moved here from
 * the notification settings); P8's Notifications (what you are told about, how it reaches you and
 * the reminder schedule, formerly /settings/notifications, which now opens here) and Appearance
 * (the colour theme). "On this page" links jump to each section (`#account`, `#notifications`,
 * `#appearance`).
 */
function Settings() {
  const { user } = useSession();
  // RequireAuth renders this only for a signed-in account.
  if (user === null) return null;

  return (
    <div className={styles.page}>
      <PageHeader title="Settings" description="Your account, how ResearchConnect AI keeps you informed, and how it looks." />

      <nav aria-label="On this page" className={styles.toc}>
        <ul>
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`} className={styles.tocLink}>
                {section.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <section id="account" className={styles.section} aria-labelledby="settings-account">
        <SectionHeader id="settings-account" title="Account" />
        <Card className={styles.card}>
          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt>Name</dt>
              <dd>{user.full_name}</dd>
            </div>
            <div className={styles.fact}>
              <dt>Email</dt>
              <dd className={styles.email}>{user.email}</dd>
            </div>
            <div className={styles.fact}>
              <dt>Account type</dt>
              <dd>{ROLE_LABELS[user.role]}</dd>
            </div>
          </dl>
          <p className={styles.note}>Only an administrator can change the account type.</p>
          <div className={styles.rule}>
            <ChangePasswordForm />
          </div>
        </Card>
      </section>

      <section id="notifications" className={styles.section} aria-labelledby="settings-notifications">
        <SectionHeader
          id="settings-notifications"
          title="Notifications"
          description="What you are told about, how it reaches you, and when deadline reminders arrive."
        />
        <Card className={styles.card}>
          <NotificationSettings />
        </Card>
      </section>

      <section id="appearance" className={styles.section} aria-labelledby="settings-appearance">
        <SectionHeader id="settings-appearance" title="Appearance" />
        <Card className={styles.card}>
          <AppearanceSettings />
        </Card>
      </section>
    </div>
  );
}

const SECTIONS = [
  { id: "account", title: "Account" },
  { id: "notifications", title: "Notifications" },
  { id: "appearance", title: "Appearance" },
];

export function SettingsPage() {
  return (
    <RequireAuth>
      <Settings />
    </RequireAuth>
  );
}
