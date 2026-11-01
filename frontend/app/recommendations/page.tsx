"use client";

import dynamic from "next/dynamic";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { SkeletonList } from "../../components/ui/State/State";
import { preloadForSession } from "../../utils/preloadForSession";

const load = () => import("../../components/recommendations/RecommendationsPage");
preloadForSession(load);
const RecommendationsPage = dynamic(() => load().then((loaded) => loaded.RecommendationsPage), { ssr: false, loading: () => <SkeletonList rows={4} lines={2} label="Loading your recommendations" /> });

/** /recommendations (P6): the signed-in researcher's recommendations and what shapes them. */
export default function RecommendationsRoute() {
  return (
    <RequireAuth roles={["STUDENT", "FACULTY"]}>
      <RecommendationsPage />
    </RequireAuth>
  );
}
