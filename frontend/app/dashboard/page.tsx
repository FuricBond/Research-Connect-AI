"use client";

/**
 * `/dashboard` — the signed-in home and the default destination after sign-in (P4). The modules
 * are in components/dashboard; RequireAuth sends a visitor to sign in and back here.
 */

import { RequireAuth } from "../../components/auth/RequireAuth";
import { Dashboard } from "../../components/dashboard/Dashboard";

export default function DashboardPage() {
  return (
    <RequireAuth>
      <Dashboard />
    </RequireAuth>
  );
}
