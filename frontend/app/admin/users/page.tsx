"use client";

import { Suspense } from "react";
import { AdminUsers } from "../../../components/admin/AdminUsers";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../components/ui/State/State";

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
