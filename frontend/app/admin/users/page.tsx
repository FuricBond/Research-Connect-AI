"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../components/ui/State/State";
import { preloadForSession } from "../../../utils/preloadForSession";

const load = () => import("../../../components/admin/AdminUsers");
preloadForSession(load);
const AdminUsers = dynamic(() => load().then((loaded) => loaded.AdminUsers), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading the accounts" /> });

/** P10 — the platform's accounts: roles, activation and verification (plan §15). */
export default function AdminUsersPage() {
  return (
    <RequireAuth roles={["ADMIN"]}>
      <Suspense fallback={<SkeletonList rows={5} lines={1} label="Loading the accounts" />}>
        <AdminUsers />
      </Suspense>
    </RequireAuth>
  );
}
