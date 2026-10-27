"use client";

/**
 * P10 — the administration overview (plan §15), the administrator's home: system health, the
 * research data monitor's summary, failed refresh passes and the accounts. The role gate only
 * decides what is worth rendering; every endpoint behind it is ADMIN only on the server.
 */

import { AdminOverview } from "../../components/admin/AdminOverview";
import { RequireAuth } from "../../components/auth/RequireAuth";

export default function AdminPage() {
  return (
    <RequireAuth roles={["ADMIN"]}>
      <AdminOverview />
    </RequireAuth>
  );
}
