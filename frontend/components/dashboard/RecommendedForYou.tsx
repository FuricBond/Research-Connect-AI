"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import type { ApiResource } from "../../hooks/useApiResource";
import type { UnifiedRecommendationResponse } from "../../types/research_intelligence";
import { humanizeEnum } from "../../utils/date";
import { DeadlineCountdown } from "../research/DeadlineCountdown";
import { MatchScore } from "../research/MatchScore";
import { Button } from "../ui/Button/Button";
import { EmptyState } from "../ui/State/State";
import { DashboardModule, Loaded } from "./Module";
import styles from "./Dashboard.module.css";

/** The explanation is code most visits never need: loaded when "Why?" is first used. */
const WhyThisRecommendationModal = dynamic(
  () => import("../personalization/WhyThisRecommendationModal").then((loaded) => loaded.WhyThisRecommendationModal),
  { ssr: false }
);

/**
 * Student "Recommended for you" (plan §8): the top three calls for this researcher, each with its
 * match band, the one main reason, and "Why?" — the existing explanation, loaded only when asked
 * for (so it is not part of the page's requests).
 */
export function RecommendedForYou({ recommendations, profileId }: { recommendations: ApiResource<UnifiedRecommendationResponse>; profileId: string }) {
  const [why, setWhy] = useState<string | null>(null);
  const interests = recommendations.data?.researcher_context?.active_interests_count;

  return (
    <DashboardModule
      id="dashboard-recommended"
      title="Recommended for you"
      action={<Link href="/researcher?section=recommendations">All recommendations</Link>}
      reserve="list"
    >
      <Loaded
        resource={recommendations}
        loading="Loading your recommendations"
        failure="Your recommendations could not be loaded."
      >
        {(data) =>
          data.recommendations.length === 0 ? (
            <EmptyState
              bare
              variant="first-use"
              headingLevel={3}
              title="No recommendations yet."
              description={
                interests === 0 ? (
                  <>
                    <Link href="/researcher?section=interests">Add your research interests</Link> and recommendations start from them.
                  </>
                ) : (
                  "New calls are matched to your interests as they arrive."
                )
              }
            />
          ) : (
            <ul className={styles.list}>
              {data.recommendations.slice(0, 3).map((item) => {
                const titleId = `recommendation-${item.opportunity_id}`;
                return (
                  <li key={item.opportunity_id} className={styles.item}>
                    <span id={titleId} className={styles.itemTitle}>
                      {item.title}
                    </span>
                    <div className={styles.meta}>
                      <MatchScore score={item.composite_score} />
                      {item.deadline && <DeadlineCountdown deadline={item.deadline} daysRemaining={item.days_remaining} />}
                      {item.opportunity_type && <span>{humanizeEnum(item.opportunity_type)}</span>}
                    </div>
                    <div className={styles.reasonRow}>
                      {item.primary_match_reason && <p className={styles.reason}>{item.primary_match_reason}</p>}
                      <Button variant="link" size="sm" aria-describedby={titleId} onClick={() => setWhy(item.opportunity_id)}>
                        Why?
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )
        }
      </Loaded>
      {why !== null && <WhyThisRecommendationModal isOpen onClose={() => setWhy(null)} researcherId={profileId} recommendationId={why} />}
    </DashboardModule>
  );
}
