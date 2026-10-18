"use client";

import { RequireAuth } from "../../components/auth/RequireAuth";
import { RecommendationsPage } from "../../components/recommendations/RecommendationsPage";

/** /recommendations (P6): the signed-in researcher's recommendations and what shapes them. */
export default function RecommendationsRoute() {
  return (
    <RequireAuth>
      <RecommendationsPage />
    </RequireAuth>
  );
}
