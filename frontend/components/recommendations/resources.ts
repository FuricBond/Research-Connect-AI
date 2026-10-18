"use client";

/**
 * P6 — what the recommendations page and the profile load, one resource per request, shared by
 * every part that asks (hooks/useApiResource.ts: account-scoped, aborted when nobody needs it,
 * a late answer never shown, nothing kept across pages or accounts).
 */

import { useApiResource } from "../../hooks/useApiResource";
import {
  fetchPersonalizationSettings,
  fetchPersonalizedRecommendations,
  fetchResearcherIntelligence,
  fetchResearcherPreferenceIntelligence,
  fetchResearcherProfile,
  fetchResearcherWorks,
} from "../../services/api";

/** How many recommendations the page lists (the API allows 100). */
export const RECOMMENDATIONS_SHOWN = 25;
/** Publications the profile lists before "Show all" (the API's page is 20). */
export const WORKS_REQUESTED = 20;

/**
 * The ranked recommendations (Phase 3.5): the same ranking the dashboard shows, with each item's
 * explanation and matched interests. Viewing them records a recommendation snapshot, as the
 * profile's recommendations did before P6 — the history and its evaluation are built from them.
 */
export function useRankedRecommendations(profileId: string | null) {
  return useApiResource(profileId ? `recommendations:ranked:${profileId}:${RECOMMENDATIONS_SHOWN}` : null, (signal) =>
    fetchPersonalizedRecommendations(profileId!, { limit: RECOMMENDATIONS_SHOWN }, undefined, signal)
  );
}

/** What the researcher stated, what was inferred from their saved calls, and the rest of Phase 5.1's view. */
export function usePreferenceIntelligence(profileId: string | null) {
  return useApiResource(profileId ? `preferences:intelligence:${profileId}` : null, (signal) =>
    fetchResearcherPreferenceIntelligence(profileId!, signal)
  );
}

/** Whether personalization, adaptive signals and feedback learning are on (Phase 5.9). */
export function usePersonalizationSettings(profileId: string | null) {
  return useApiResource(profileId ? `personalization:settings:${profileId}` : null, (signal) =>
    fetchPersonalizationSettings(profileId!, undefined, signal)
  );
}

export function useResearcherProfile(profileId: string | null) {
  return useApiResource(profileId ? `researcher:profile:${profileId}` : null, (signal) => fetchResearcherProfile(profileId!, signal));
}

/** The publications linked to the researcher (asked only once the profile is linked to a scholar). */
export function useResearcherWorks(profileId: string | null) {
  return useApiResource(profileId ? `researcher:works:${profileId}:${WORKS_REQUESTED}` : null, (signal) =>
    fetchResearcherWorks(profileId!, WORKS_REQUESTED, 0, signal)
  );
}

/**
 * Topics drawn from the researcher's publications (Phase 3.2). `refresh` recomputes them, which a
 * profile edit needs; the key keeps the two apart so a recomputation is its own request.
 */
export function useResearchTopics(profileId: string | null, refresh: number) {
  return useApiResource(profileId ? `researcher:topics:${profileId}:${refresh}` : null, (signal) =>
    fetchResearcherIntelligence(profileId!, refresh > 0, signal)
  );
}
