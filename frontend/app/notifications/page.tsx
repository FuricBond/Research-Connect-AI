"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { NotificationsPage } from "../../components/notifications/NotificationsPage";

/** P8 — the notifications, grouped by source (components/notifications). */
export default function NotificationsPageRoute() {
  return (
    <RequireAuth>
      <Suspense fallback={null}>
        <NotificationsPage />
      </Suspense>
    </RequireAuth>
  );
}
