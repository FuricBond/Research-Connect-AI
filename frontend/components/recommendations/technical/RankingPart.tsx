"use client";

import { useState } from "react";
import { useApiResource } from "../../../hooks/useApiResource";
import { fetchPersonalizedRecommendations } from "../../../services/api";
import type { AblationSummary, PersonalizedRankedCandidate, PersonalizedRankingResponse } from "../../../types/researcher";
import { DeadlineCountdown } from "../../research/DeadlineCountdown";
import { Fact } from "../../research/RiskDetails";
import { RiskIndicator } from "../../research/RiskIndicator";
import { Button } from "../../ui/Button/Button";
import { Checkbox, Select } from "../../ui/Field/Field";
import details from "../../research/Details.module.css";
import { Loaded, Metrics, decimal, signedDecimal } from "./shared";
import styles from "../Recommendations.module.css";

interface Options {
  personalization: boolean;
  inferred: boolean;
  expertise: boolean;
  limit: number;
}

function Ablation({ summary }: { summary: AblationSummary }) {
  return (
    <Metrics
      label="Personalized ranking compared with relevance alone"
      items={[
        ["Calls ranked", summary.total_candidates],
        ["Moved by personalization", summary.reordered_candidates_count],
        ["Largest move up / down", `+${summary.max_rank_promotion} / ${summary.max_rank_demotion}`],
        ["Average adjustment", signedDecimal(summary.average_personalization_adjustment, 4)],
        ["Order checks", summary.invariants_verified ? "Passed" : "Failed"],
      ]}
    />
  );
}

function Movement({ delta }: { delta: number }) {
  if (delta > 0) return <>up {delta}</>;
  if (delta < 0) return <>down {-delta}</>;
  return <>unchanged</>;
}

function Candidate({ item }: { item: PersonalizedRankedCandidate }) {
  const breakdown = item.score_breakdown;
  const matched = [...item.matched_signals.matched_preferences, ...item.matched_signals.matched_expertise, ...item.matched_signals.matched_topics];
  return (
    <li className={styles.record}>
      <span className={styles.recordHead}>
        <span className={styles.numbers}>#{item.rank}</span>
        <span className={styles.recordTitle}>{item.opportunity.title}</span>
      </span>
      <span className={styles.numbers}>
        Before personalization #{item.base_rank} (<Movement delta={item.rank_delta} />) · final {decimal(item.final_score, 4)} · relevance {decimal(item.base_relevance_score)} · adjustment{" "}
        {signedDecimal(item.personalization_adjustment)}
      </span>
      <details className={details.technical}>
        <summary>
          Score breakdown<span className="rc-visually-hidden"> for {item.opportunity.title}</span>
        </summary>
        <div className={details.technicalBody}>
          <dl className={details.facts}>
            <Fact term="Relevance" value={decimal(item.base_relevance_score, 4)} />
            <Fact term="Stated preferences (40%)" value={decimal(breakdown.explicit_preference_score, 4)} />
            <Fact term="Inferred preferences (15%)" value={decimal(breakdown.inferred_preference_score, 4)} />
            <Fact term="Expertise in your publications (25%)" value={decimal(breakdown.expertise_match_score, 4)} />
            <Fact term="Profile (10%)" value={decimal(breakdown.profile_match_score, 4)} />
            {typeof breakdown.behavioral_score === "number" && <Fact term="Learned from your activity" value={signedDecimal(breakdown.behavioral_adjustment ?? 0, 4)} />}
            <Fact term="Relevance damping" value={decimal(breakdown.relevance_damping, 4)} />
            <Fact term="Adjustment (at most 0.15)" value={signedDecimal(item.personalization_adjustment, 4)} />
            <Fact term="Final score" value={decimal(item.final_score, 4)} />
            <Fact term="Matched" value={matched.length > 0 ? matched.join(", ") : "No preference or expertise matched (found by discovery)"} />
            <Fact term="Venue risk" value={<RiskIndicator level={item.opportunity.risk_level} isPredatory={item.opportunity.is_predatory_flag} />} />
            <Fact
              term="Deadline"
              value={
                <DeadlineCountdown
                  deadline={item.opportunity.submission_deadline}
                  daysRemaining={item.opportunity.days_remaining}
                  status={item.opportunity.deadline_status}
                  urgencyTier={item.opportunity.urgency_tier}
                />
              }
            />
          </dl>
        </div>
      </details>
    </li>
  );
}

function Compared({ profileId, options }: { profileId: string; options: Options }) {
  const key = `technical:ranking:${profileId}:${options.personalization}:${options.inferred}:${options.expertise}:${options.limit}`;
  const ranking = useApiResource(key, (signal) =>
    fetchPersonalizedRecommendations(
      profileId,
      {
        limit: options.limit,
        includeInferred: options.inferred,
        includeExpertise: options.expertise,
        enablePersonalization: options.personalization,
        includeAblation: true,
      },
      undefined,
      signal
    )
  );
  return (
    <Loaded resource={ranking} label="Ranking the calls again" failure="That ranking could not be made.">
      {(data) => (
        <>
          {data.ablation_summary && <Ablation summary={data.ablation_summary} />}
          {data.recommendations.length === 0 ? (
            <p className={styles.muted}>No calls to rank with these settings.</p>
          ) : (
            <ol className={styles.records} aria-label="Calls in this ranking">
              {data.recommendations.map((item) => (
                <Candidate key={item.opportunity_id} item={item} />
              ))}
            </ol>
          )}
        </>
      )}
    </Loaded>
  );
}

/**
 * The ranking with and without personalization (Phase 3.5's comparison, formerly "Personalized
 * Recommendation Ranking" on the profile): how much personalization moved this page's list, and
 * a ranking made on request with parts of it switched off, each call with its score breakdown.
 * As before, every ranking made here is kept in the recommendation history.
 */
export default function RankingPart({ profileId, ranking }: { profileId: string; ranking: PersonalizedRankingResponse | null }) {
  const [draft, setDraft] = useState<Options>({ personalization: true, inferred: true, expertise: true, limit: 20 });
  const [asked, setAsked] = useState<Options | null>(null);

  return (
    <>
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>This page&apos;s ranking</h4>
        {ranking?.ablation_summary ? <Ablation summary={ranking.ablation_summary} /> : <p className={styles.muted}>No comparison was returned with this ranking.</p>}
        {ranking && (
          <p className={styles.muted}>
            Personalization can change a score by at most {decimal(ranking.max_personalization_contribution, 2)}; {ranking.total_candidates} calls were considered.
          </p>
        )}
      </div>
      <form
        className={styles.group}
        onSubmit={(event) => {
          event.preventDefault();
          setAsked({ ...draft });
        }}
      >
        <h4 className={styles.groupTitle}>Rank with parts switched off</h4>
        <div className={styles.controls}>
          <Checkbox label="Personalization" checked={draft.personalization} onChange={(event) => setDraft({ ...draft, personalization: event.target.checked })} />
          <Checkbox label="Inferred preferences" checked={draft.inferred} onChange={(event) => setDraft({ ...draft, inferred: event.target.checked })} />
          <Checkbox label="Expertise in your publications" checked={draft.expertise} onChange={(event) => setDraft({ ...draft, expertise: event.target.checked })} />
          <Select label="Calls" value={String(draft.limit)} onChange={(event) => setDraft({ ...draft, limit: Number(event.target.value) })}>
            {[10, 20, 50].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <Button type="submit" variant="secondary" size="sm">
            Rank
          </Button>
        </div>
        <p className={styles.muted}>Each ranking made here is kept in your recommendation history.</p>
      </form>
      {asked && <Compared profileId={profileId} options={asked} />}
    </>
  );
}
