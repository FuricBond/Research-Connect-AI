import type { Metadata } from "next";
import { SettingsPage } from "../../components/settings/SettingsPage";

export const metadata: Metadata = {
  title: "Settings — ResearchConnect AI",
};

/** P3 — the account settings (`/settings`); the notification settings stay at `/settings/notifications`. */
export default function SettingsRoute() {
  return <SettingsPage />;
}
