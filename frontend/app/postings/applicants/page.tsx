"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { ApplicantsInbox } from "../../../components/postings/ApplicantsInbox";
import { SkeletonList } from "../../../components/ui/State/State";

/** P9 — the applicant inbox across a faculty member's postings (plan §14). */
export default function ApplicantsPage() {
  return (
    <RequireAuth roles={["FACULTY", "ADMIN"]}>
      <Suspense fallback={<SkeletonList rows={3} lines={3} label="Loading your applicants" />}>
        <ApplicantsInbox />
      </Suspense>
    </RequireAuth>
  );
}
