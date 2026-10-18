"use client";

import { Suspense } from "react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { ProfilePage } from "../../components/profile/ProfilePage";

/**
 * /researcher (P6): the researcher's profile — summary, publications, research topics and the way
 * to preferences. The P0.4 sections' links still work: ?section=recommendations, personalization
 * and history open /recommendations, where the recommendations and their diagnostics now live;
 * ?section=interests opens this page's research topics.
 */
export default function ResearcherPageRoute() {
  return (
    <RequireAuth>
      {/* useSearchParams needs a boundary for this route to prerender. */}
      <Suspense fallback={null}>
        <ProfilePage />
      </Suspense>
    </RequireAuth>
  );
}
