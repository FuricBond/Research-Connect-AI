"use client";

import dynamic from "next/dynamic";
import { SkeletonList } from "../../components/ui/State/State";

/** A tool opened from a paper; everything it shows depends on the browser's session (audit PERF-04). */
export const VenuesRoute = dynamic(() => import("../../components/pages/OpportunityMatches").then((loaded) => loaded.OpportunityMatchesPage), {
  ssr: false,
  loading: () => <SkeletonList rows={4} lines={3} label="Loading" />,
});
