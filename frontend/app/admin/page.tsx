"use client";

/**
 * P10 — the administration overview (plan §15), the administrator's home: system health, the
 * research data monitor's summary, failed refresh passes and the accounts. The role gate only
 * decides what is worth rendering; every endpoint behind it is ADMIN only on the server.
 */

import dynamic from "next/dynamic";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { SkeletonList } from "../../components/ui/State/State";
import { preloadForSession } from "../../utils/preloadForSession";

const load = () => import("../../components/admin/AdminOverview");
preloadForSession(load);
const AdminOverview = dynamic(() => load().then((loaded) => loaded.AdminOverview), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading the overview" /> });

export default function AdminPage() {
  return (
    <RequireAuth roles={["ADMIN"]}>
      <AdminOverview />
    </RequireAuth>
  );
}
