"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { SubmissionsPage } from "../../components/workspace/SubmissionsPage";

/** P7 — every submission in one list (components/workspace/SubmissionsPage). */
export default function SubmissionsRoute() {
  return (
    <RequireAuth>
      <Suspense fallback={null}>
        <SubmissionsPage />
      </Suspense>
    </RequireAuth>
  );
}
