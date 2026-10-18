"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { CalendarPage } from "../../components/calendar/CalendarPage";

/** P7 — deadlines and milestones (components/calendar/CalendarPage). */
export default function CalendarPageRoute() {
  return (
    <RequireAuth>
      <Suspense fallback={null}>
        <CalendarPage />
      </Suspense>
    </RequireAuth>
  );
}
