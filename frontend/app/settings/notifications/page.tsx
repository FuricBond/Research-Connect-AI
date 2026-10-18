import { redirect } from "next/navigation";

/**
 * P8 — the notification settings are a section of Settings now (plan: /settings with Account,
 * Notifications and Appearance). The old address keeps working for bookmarks and old links.
 */
export default function NotificationSettingsRedirect(): never {
  return redirect("/settings#notifications");
}
