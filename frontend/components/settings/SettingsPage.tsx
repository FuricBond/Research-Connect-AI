"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ROLE_LABELS } from "../../types/auth";
import { RequireAuth } from "../auth/RequireAuth";
import { ChangePasswordForm } from "../auth/ChangePasswordForm";
import { useSession } from "../auth/SessionProvider";
import { Card } from "../ui/Card/Card";
import { PageHeader, SectionHeader } from "../ui/PageHeader/PageHeader";
import styles from "./SettingsPage.module.css";

/**
 * P3 — Settings (`/settings`): the account (who is signed in, and the password change moved here
 * from the notification settings) and the way to the notification settings. The notification
 * and appearance sections join this page in P8; until then the theme stays in the account menu.
 */
function Settings() {
  const { user } = useSession();
  // RequireAuth renders this only for a signed-in account.
  if (user === null) return null;

  return (
    <div className={styles.page}>
      <PageHeader title="Settings" description="Your account, and how ResearchConnect AI keeps you informed." />

      <section className={styles.section} aria-labelledby="settings-account">
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

      <section className={styles.section} aria-labelledby="settings-notifications">
        <SectionHeader
          id="settings-notifications"
          title="Notifications"
          description="Which alerts you get, how they reach you, and when deadline reminders arrive."
        />
        <Link href="/settings/notifications" className={styles.onward}>
          Notification settings
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </section>
    </div>
  );
}

export function SettingsPage() {
  return (
    <RequireAuth>
      <Settings />
    </RequireAuth>
  );
}
