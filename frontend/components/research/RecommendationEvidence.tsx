"use client";

import { useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import {
  fetchHistoricalRecommendationExplanation,
  fetchOpportunityPersonalization,
  fetchRecommendationPersonalizationExplanation,
  getOpportunityIntelligence,
} from "../../services/api";
import type { MatchedPersonalizationSignals, PersonalizationScoreBreakdown, RecommendationExplanation } from "../../types/researcher";
import { humanizeEnum } from "../../utils/date";
import {
  PERSONALIZATION_FACTOR_GROUPS,
  confidenceLabel,
  factorCategoryLabel,
  impactWord,
  personalizationImpactLabel,
  preferenceMatchLabel,
  uniqueWords,
  withoutMark,
  wordedSuffix,
} from "../../utils/personalization";
import { Button } from "../ui/Button/Button";
import { SkeletonList } from "../ui/State/State";
import { MatchScore } from "./MatchScore";
import { Fact } from "./RiskDetails";
import { ScoreMeter } from "./ScoreMeter";
import { TopicTags } from "./TopicTags";
import styles from "./Details.module.css";

/** A recommendation as the Evidence panel explains it (one item of a recommendation list). */
export interface RecommendationSubject {
  profileId: string;
  opportunityId: string;
  rank?: number | null;
  /** Where the item sat before personalization (the API's base rank). */
  baseRank?: number | null;
  finalScore: number | null;
  relevanceScore: number | null;
  personalizationScore: number | null;
  personalizationAdjustment?: number | null;
  /** False when personalization is paused: only relevance counted. Unknown is null. */
  personalizationEnabled?: boolean | null;
  explanation: Partial<RecommendationExplanation> | null;
  matched?: MatchedPersonalizationSignals | null;
  breakdown?: PersonalizationScoreBreakdown | null;
  /** A recommendation from the history: its explanation is as it was then; nothing live is asked. */
  historical?: boolean;
  /** The kept list it came from; with no explanation given, the one kept then is asked for. */
  snapshotId?: string;
}

const list = (values: readonly string[] | null | undefined) =>
  (values ?? []).filter((value) => typeof value === "string" && value.trim()).map(withoutMark);
const signed = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(4)}`;

function ReasonGroup({ title, reasons }: { title: string; reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <div className={styles.group}>
      <h4 className={styles.groupTitle}>{title}</h4>
      <ul className={styles.list}>
        {reasons.map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

/** How the researcher's preferences and activity shaped it (Phase 5.9), asked for when the panel opens. */
function PersonalizationPart({ subject }: { subject: RecommendationSubject }) {
  const why = useApiResource(subject.historical ? null : `recommendation-why:${subject.profileId}:${subject.opportunityId}`, (signal) =>
    fetchRecommendationPersonalizationExplanation(subject.profileId, subject.opportunityId, undefined, signal)
  );
  if (subject.historical) {
    return <p className={styles.muted}>This explanation is from the time it was recommended; how your activity shapes it now is on the current recommendation.</p>;
  }
  if (why.status === "loading" || why.status === "idle") return <SkeletonList rows={2} label="Loading how your activity shaped it" announce={false} />;
  if (why.status === "error" || !why.data) {
    return (
      <div className={styles.group}>
        <p className={styles.text}>{why.error?.kind === "not-found" ? "There is no personalization record for this recommendation." : "This part of the explanation could not be loaded."}</p>
        {why.error?.kind !== "not-found" && (
          <div>
            <Button size="sm" onClick={why.retry}>
              Try again
            </Button>
          </div>
        )}
      </div>
    );
  }
  const data = why.data;
  return (
    <>
      <p className={styles.text}>
        <strong>{personalizationImpactLabel(data.personalization_impact)}.</strong> {data.deterministic_explanation}
      </p>
      {PERSONALIZATION_FACTOR_GROUPS.map(({ key, label }) => (
        <ReasonGroup key={key} title={label} reasons={list((data[key] ?? []).map((factor) => factor.summary))} />
      ))}
      {data.governance_notes && <p className={styles.muted}>{data.governance_notes}</p>}
      <ReasonGroup title="In short" reasons={list(data.contributing_factors_summary).map(withoutMark)} />
    </>
  );
}

/** The fuller records behind it — the evidence tiers and the preference assessment — asked for only when opened. */
function TechnicalRecords({ subject }: { subject: RecommendationSubject }) {
  const tiers = useApiResource(`recommendation-tiers:${subject.profileId}:${subject.opportunityId}`, (signal) =>
    getOpportunityIntelligence(subject.profileId, subject.opportunityId, undefined, signal)
  );
  const assessment = useApiResource(`recommendation-assessment:${subject.profileId}:${subject.opportunityId}`, (signal) =>
    fetchOpportunityPersonalization(subject.profileId, subject.opportunityId, undefined, signal)
  );
  return (
    <>
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Evidence tiers</h4>
        {tiers.status === "loading" || tiers.status === "idle" ? (
          <SkeletonList rows={2} label="Loading the evidence tiers" announce={false} />
        ) : tiers.status === "error" || !tiers.data ? (
          <p className={styles.muted}>
            The evidence tiers could not be loaded.{" "}
            <Button variant="link" size="sm" onClick={tiers.retry}>
              Try again
            </Button>
          </p>
        ) : (
          <ul className={styles.list}>
            {tiers.data.evidence_tiers.map((tier, i) => (
              <li key={i}>
                <strong>{tier.tier_title}</strong> — {tier.status_label ? humanizeEnum(tier.status_label) : signed(tier.score_contribution)}
                {tier.is_active ? "" : " (not active)"}. {tier.summary}
                {tier.signals.length > 0 && (
                  <span className={styles.source}> Signals: {tier.signals.map((signal) => `${signal.evidence || humanizeEnum(signal.signal_type)} (${signal.strength.toFixed(2)})`).join("; ")}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className={styles.group}>
        <h4 className={styles.groupTitle}>Preference assessment</h4>
        {assessment.status === "loading" || assessment.status === "idle" ? (
          <SkeletonList rows={2} label="Loading the preference assessment" announce={false} />
        ) : assessment.status === "error" || !assessment.data ? (
          <p className={styles.muted}>
            The preference assessment could not be loaded.{" "}
            <Button variant="link" size="sm" onClick={assessment.retry}>
              Try again
            </Button>
          </p>
        ) : (
          <>
            <p className={styles.text}>
              {preferenceMatchLabel(assessment.data.preference_assessment.overall_match_state)}. {assessment.data.preference_assessment.deterministic_explanation}
            </p>
            <dl className={styles.facts}>
              <Fact term="Personalization score" value={assessment.data.personalization_score.toFixed(4)} />
              <Fact term="Bounded score" value={assessment.data.score.bounded_score.toFixed(4)} />
              <Fact term="Confidence" value={assessment.data.score.confidence.toFixed(2)} />
              <Fact term="Preferences that matched" value={String(assessment.data.preference_assessment.positive_matches_count)} />
              <Fact term="Preferences that exclude it" value={String(assessment.data.preference_assessment.excluded_matches_count)} />
              <Fact term="Conflicts" value={String(assessment.data.preference_assessment.conflict_count)} />
              <Fact term="Evidence coverage" value={assessment.data.preference_assessment.evidence_coverage.toFixed(2)} />
              {typeof assessment.data.adaptive_score === "number" && <Fact term="Adaptive score" value={assessment.data.adaptive_score.toFixed(4)} />}
              {typeof assessment.data.calibration_score === "number" && <Fact term="Calibration score" value={assessment.data.calibration_score.toFixed(4)} />}
              {typeof assessment.data.contextual_score === "number" && <Fact term="Contextual score" value={assessment.data.contextual_score.toFixed(4)} />}
            </dl>
            <ReasonGroup title="Counted for it" reasons={list(assessment.data.explanation.positive_reasons)} />
            <ReasonGroup title="Counted against it" reasons={list(assessment.data.explanation.negative_reasons)} />
            <ReasonGroup title="Not resolved" reasons={[...list(assessment.data.explanation.unresolved_reasons), ...list(assessment.data.explanation.insufficient_evidence_reasons)]} />
          </>
        )}
      </div>
    </>
  );
}

/**
 * "Why this match?" for a recommendation, inside the Evidence panel (plan §12: one explanation UI
 * replaces the two recommendation modals). It shows what the API returned with the recommendation —
 * the scores, the matched interests, the reasons by where they come from, the factors — then how
 * the researcher's preferences and activity shaped it (asked for when the panel opens), and the
 * fuller records behind "Technical details" (asked for when opened). Nothing is added to the API's
 * words; a missing part says so.
 */
export function RecommendationEvidence({ subject, headingId }: { subject: RecommendationSubject; headingId: string }) {
  if (subject.historical && subject.snapshotId && !subject.explanation) return <KeptEvidence subject={subject} snapshotId={subject.snapshotId} headingId={headingId} />;
  return <Evidence subject={subject} headingId={headingId} />;
}

/** A recommendation from a kept list: its explanation as it was then (Phase 3.8), asked for when the panel opens. */
function KeptEvidence({ subject, snapshotId, headingId }: { subject: RecommendationSubject; snapshotId: string; headingId: string }) {
  const kept = useApiResource(`recommendation-then:${subject.profileId}:${snapshotId}:${subject.opportunityId}`, (signal) =>
    fetchHistoricalRecommendationExplanation(subject.profileId, snapshotId, subject.opportunityId, undefined, signal)
  );
  if (kept.status === "loading" || kept.status === "idle") return <SkeletonList rows={3} label="Loading the explanation kept with it" />;
  if (kept.status === "error" || !kept.data) {
    return (
      <section className={styles.section} aria-labelledby={`${headingId}-match`}>
        <h3 id={`${headingId}-match`} tabIndex={-1} className={styles.sectionTitle}>
          How well it matched you
        </h3>
        <p className={styles.text}>{kept.error?.kind === "not-found" ? "No explanation was kept for this recommendation." : "The explanation kept with it could not be loaded."}</p>
        {kept.error?.kind !== "not-found" && (
          <div>
            <Button size="sm" onClick={kept.retry}>
              Try again
            </Button>
          </div>
        )}
      </section>
    );
  }
  return <Evidence subject={{ ...subject, explanation: kept.data }} headingId={headingId} />;
}

function Evidence({ subject, headingId }: { subject: RecommendationSubject; headingId: string }) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const explanation = subject.explanation;
  const matched = subject.matched;
  // Expertise reads "Accessibility (PRIMARY_EXPERTISE)": the topic is what matched; the same topic
  // in another case is one topic.
  const topics = uniqueWords([...list(matched?.matched_topics), ...list(matched?.matched_expertise).map((entry) => entry.replace(/\s*\([^)]*\)\s*$/, ""))]);
  const preferences = uniqueWords(list(matched?.matched_preferences).map(wordedSuffix));
  const movedBy = subject.baseRank && subject.rank ? subject.baseRank - subject.rank : 0;
  const summary = list(explanation?.primary_reasons)[0] ?? null;

  return (
    <>
      <section className={styles.section} aria-labelledby={`${headingId}-match`}>
        <h3 id={`${headingId}-match`} tabIndex={-1} className={styles.sectionTitle}>
          {subject.historical ? "How well it matched you" : "How well it matches you"}
        </h3>
        <div className={styles.cluster}>
          <MatchScore score={subject.finalScore} kind="match" />
          {subject.rank ? <span className={styles.muted}>Ranked #{subject.rank}</span> : null}
          {movedBy !== 0 && (
            <span className={styles.muted}>
              {movedBy > 0 ? `Moved up ${movedBy} place${movedBy === 1 ? "" : "s"}` : `Moved down ${-movedBy} place${movedBy === -1 ? "" : "s"}`} by your preferences
            </span>
          )}
        </div>
        {summary && <p className={styles.text}>{summary}</p>}
        {!explanation && <p className={styles.muted}>No explanation was returned for this recommendation.</p>}
        {subject.personalizationEnabled === false && (
          <p className={styles.muted}>Personalization is paused, so only relevance to your research counted.</p>
        )}
        <div className={styles.meters} role="group" aria-label="What counted">
          {subject.relevanceScore !== null && (
            <ScoreMeter name="Relevance to your research" score={subject.relevanceScore} description="How close the call is to your research, before any preference is applied." />
          )}
          {subject.personalizationScore !== null && (
            <ScoreMeter
              name="Your preferences and activity"
              score={subject.personalizationScore}
              available={subject.personalizationEnabled !== false}
              description="How well it fits what you stated and did; it can move a recommendation only a little."
            />
          )}
        </div>
        {topics.length > 0 && (
          <div className={styles.group}>
            <h4 className={styles.groupTitle}>Matched in your research</h4>
            <TopicTags topics={topics} shared label="Matched topics" />
          </div>
        )}
        {preferences.length > 0 && (
          <div className={styles.group}>
            <h4 className={styles.groupTitle}>Matched in your preferences</h4>
            <TopicTags topics={preferences} shared label="Matched preferences" />
          </div>
        )}
        <ReasonGroup title="From your publications" reasons={list(explanation?.expertise_reasons)} />
        <ReasonGroup title="From your preferences" reasons={list(explanation?.preference_reasons)} />
        <ReasonGroup title="From your feedback" reasons={list(explanation?.behavioral_reasons)} />
        <ReasonGroup
          title="Also"
          reasons={(() => {
            const shown = new Set([summary, ...list(explanation?.expertise_reasons), ...list(explanation?.preference_reasons), ...list(explanation?.behavioral_reasons)]);
            return uniqueWords([...list(explanation?.primary_reasons).slice(1), ...list(explanation?.supporting_reasons)]).filter((reason) => !shown.has(reason));
          })()}
        />
        <ReasonGroup title="Counted against it" reasons={list(explanation?.negative_signals)} />
        {(explanation?.factors ?? []).length > 0 && (
          <div className={styles.group}>
            <h4 className={styles.groupTitle}>What counted</h4>
            <ol className={styles.list}>
              {(explanation?.factors ?? []).map((factor, i) => (
                <li key={i}>
                  <strong>{factorCategoryLabel(factor.category)}</strong> — {factor.description || factor.title}{" "}
                  <span className={styles.source}>({impactWord(factor.impact)})</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {(explanation?.risk_summary || explanation?.deadline_summary) && (
          <div className={styles.group}>
            <h4 className={styles.groupTitle}>Trust and timing</h4>
            <ul className={styles.list}>
              {explanation?.risk_summary && <li>{explanation.risk_summary}</li>}
              {explanation?.deadline_summary && <li>{explanation.deadline_summary}</li>}
            </ul>
          </div>
        )}
      </section>

      <section className={styles.section} aria-labelledby={`${headingId}-activity`}>
        <h3 id={`${headingId}-activity`} className={styles.sectionTitle}>
          How your preferences and activity shaped it
        </h3>
        <PersonalizationPart subject={subject} />
      </section>

      <details className={styles.technical} onToggle={(event) => setTechnicalOpen((event.currentTarget as HTMLDetailsElement).open)}>
        <summary>Technical details</summary>
        <div className={styles.technicalBody}>
          <dl className={styles.facts}>
            {subject.finalScore !== null && <Fact term="Final score" value={subject.finalScore.toFixed(4)} />}
            {subject.relevanceScore !== null && <Fact term="Relevance score" value={subject.relevanceScore.toFixed(4)} />}
            {subject.personalizationScore !== null && <Fact term="Personalization score" value={subject.personalizationScore.toFixed(4)} />}
            {typeof subject.personalizationAdjustment === "number" && <Fact term="Personalization adjustment" value={signed(subject.personalizationAdjustment)} />}
            {subject.rank ? <Fact term="Rank" value={subject.baseRank ? `${subject.rank} (before personalization ${subject.baseRank})` : String(subject.rank)} /> : null}
            {confidenceLabel(explanation?.confidence) && <Fact term="Confidence" value={confidenceLabel(explanation?.confidence)} />}
            {explanation?.trust_status && <Fact term="Venue trust" value={explanation.trust_status} />}
            {explanation?.personalization_strength && <Fact term="Personalization strength" value={humanizeEnum(explanation.personalization_strength)} />}
            {explanation?.ranking_version && <Fact term="Ranking version" value={explanation.ranking_version} />}
            {subject.breakdown &&
              (Object.entries(subject.breakdown) as [string, number | undefined][])
                .filter((entry): entry is [string, number] => typeof entry[1] === "number")
                .map(([key, value]) => <Fact key={key} term={humanizeEnum(key)} value={value.toFixed(4)} />)}
          </dl>
          {technicalOpen && !subject.historical && <TechnicalRecords subject={subject} />}
        </div>
      </details>
    </>
  );
}
