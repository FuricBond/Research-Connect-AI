"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";
import { RequireAuth } from "../../../components/auth/RequireAuth";
import { SkeletonList } from "../../../components/ui/State/State";
import { preloadForSession } from "../../../utils/preloadForSession";

const load = () => import("../../../components/postings/ApplicantsInbox");
preloadForSession(load);
const ApplicantsInbox = dynamic(() => load().then((loaded) => loaded.ApplicantsInbox), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading your applicants" /> });

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
