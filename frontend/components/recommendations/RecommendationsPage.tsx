"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PersonalizedRankedCandidate, PersonalizedRankingResponse } from "../../types/researcher";
import type { WorkspaceItem } from "../../types/workspace";
import { useSession } from "../auth/SessionProvider";
import { EvidencePanel } from "../research/lazyPanels";
import { useTrackedCalls } from "../research/trackedCalls";
import { PageHeader } from "../ui/PageHeader/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../ui/State/State";
import { groupHeading, groupRecommendations } from "./grouping";
import { RecommendationCard } from "./RecommendationCard";
import { usePersonalizationSettings, usePreferenceIntelligence, useRankedRecommendations } from "./resources";
import { TechnicalDetails } from "./TechnicalDetails";
import { TransparencyPanel } from "./TransparencyPanel";
import styles from "./Recommendations.module.css";

function rankingNote(ranked: { ranked_count: number; personalization_enabled: boolean; is_cold_start: boolean }): string {
  const count = `${ranked.ranked_count} call${ranked.ranked_count === 1 ? "" : "s"}`;
  if (!ranked.personalization_enabled) return `${count}, ranked by relevance to your research alone: personalization is off.`;
  if (ranked.is_cold_start) return `${count}, ranked by relevance to your research. Add interests or save calls and the ranking adapts to them.`;
  return `${count}, ranked by relevance to your research and adjusted a little by your preferences and activity.`;
}

/**
 * P6 — /recommendations (plan §12): the calls ranked for the researcher (Phase 3.5, the ranking
 * the dashboard shows), grouped by the interest each matched — "Because you follow …" — with
 * the match band, the API's main reason, "Why this match?" (the shared Evidence panel), Save and
 * Helpful / Not relevant. Beside it, what shapes the ranking and the controls over it; below it,
 * the technical details, each part loaded only when opened. Four requests besides the shell's.
 */
export function RecommendationsPage() {
  const { profileId } = useSession();
  const ranked = useRankedRecommendations(profileId);
  const preferences = usePreferenceIntelligence(profileId);
  const settings = usePersonalizationSettings(profileId);
  const tracked = useTrackedCalls();
  const [savedNow, setSavedNow] = useState<Set<string>>(() => new Set());
  const [why, setWhy] = useState<PersonalizedRankedCandidate | null>(null);

  const onSaved = (item: WorkspaceItem) => setSavedNow((current) => new Set(current).add(item.opportunity_id));
  // A re-ranking (after a change beside the list) keeps the last list on screen until the new one
  // is in, and what sits below or beside the list appears once the first list is in: nothing
  // moves while the page loads or re-ranks (CLS), and the panel keeps its state.
  const [lastRanking, setLastRanking] = useState<PersonalizedRankingResponse | null>(null);
  useEffect(() => {
    if (ranked.data) setLastRanking(ranked.data);
  }, [ranked.data]);
  const reranking = ranked.status === "loading" && lastRanking !== null;
  const ranking = ranked.data ?? (reranking ? lastRanking : null);
  const listSettled = ranking !== null || ranked.status === "error" || ranked.status === "empty";
  const groups = ranking ? groupRecommendations(ranking.recommendations) : [];

  return (
    <>
      <PageHeader
        title="Recommendations"
        description="Calls for papers matched to your research and preferences, with the reasons behind each match."
      />
      {!profileId ? (
        <EmptyState
          headingLevel={2}
          title="Your researcher profile is not set up yet."
          description={
            <>
              Recommendations are matched to a researcher profile. <Link href="/researcher">Set up your profile</Link>.
            </>
          }
        />
      ) : (
        <div className={styles.layout}>
          <div className={styles.main} aria-busy={ranked.status === "loading" || undefined}>
            {!listSettled ? (
              <div className={styles.loading}>
                {/* Text in the card title face, so its font loads with the first paint, not with the
                    titles (a re-wrapped title would move the list). Hidden, and not read out. */}
                <span className={styles.fontPrimer} aria-hidden="true">
                  Recommendations
                </span>
                <SkeletonList rows={4} lines={3} label="Loading your recommendations" />
              </div>
            ) : !ranking ? (
              <ErrorState headingLevel={2} title="Your recommendations could not be loaded" kind={ranked.error?.kind === "network" ? "offline" : "failed"} onRetry={ranked.retry} />
            ) : ranking.recommendations.length === 0 ? (
              <EmptyState
                headingLevel={2}
                title="No recommendations yet."
                description={
                  <>
                    New calls are matched to your research as they arrive. <Link href="/researcher/preferences">Add research preferences</Link> or{" "}
                    <Link href="/browse">browse calls for papers</Link>.
                  </>
                }
              />
            ) : (
              <>
                <p className={styles.status} role="status">
                  {reranking ? "Ranking again with your change…" : rankingNote(ranking)}
                </p>
                {groups.map((group) => {
                  const heading = groupHeading(group);
                  const headingId = `group-${group.key.replace(/[^a-z0-9]+/gi, "-")}`;
                  return (
                    <section key={group.key} className={styles.section} aria-labelledby={headingId}>
                      <h2 id={headingId} className={styles.sectionTitle}>
                        {heading.lead}
                        {heading.topic && (
                          <>
                            {" "}
                            <em>{heading.topic}</em>
                          </>
                        )}
                      </h2>
                      <ul className={styles.list}>
                        {group.items.map((item) => (
                          <li key={item.opportunity_id}>
                            <RecommendationCard
                              item={item}
                              profileId={profileId}
                              saved={tracked.byCall.has(item.opportunity_id) || savedNow.has(item.opportunity_id)}
                              onSaved={onSaved}
                              onExplain={setWhy}
                            />
                          </li>
                        ))}
                      </ul>
                    </section>
                  );
                })}
              </>
            )}
            {listSettled && <TechnicalDetails profileId={profileId} ranking={ranking} preferences={preferences.data ?? null} onRankingChanged={ranked.retry} />}
          </div>

          {listSettled && <TransparencyPanel profileId={profileId} preferences={preferences} settings={settings} onRankingChanged={ranked.retry} />}
        </div>
      )}

      {why && profileId && (
        <EvidencePanel
          subject={{
            title: why.opportunity.title,
            context: "recommendation",
            rank: why.rank,
            score: why.final_score,
            scoreKind: "match",
            explanation: null,
            recommendation: {
              profileId,
              opportunityId: why.opportunity_id,
              rank: why.rank,
              baseRank: why.base_rank,
              finalScore: why.final_score,
              relevanceScore: why.base_relevance_score,
              personalizationScore: why.personalization_score,
              personalizationAdjustment: why.personalization_adjustment,
              personalizationEnabled: ranking?.personalization_enabled ?? null,
              explanation: why.explanation ?? null,
              matched: why.matched_signals,
              breakdown: why.score_breakdown,
            },
          }}
          onClose={() => setWhy(null)}
        />
      )}
    </>
  );
}
