"use client";

import { useEffect, useId, useRef } from "react";
import type { ExplanationSchema } from "../../types/discovery";
import type { OpportunityDeadline, RiskExplanation } from "../../types/opportunity";
import { assessmentWord, citationsLabel, countedSignals, plainSummary, signalDescription, signalName, type ExplanationContext } from "../../utils/research";
import { Drawer } from "../ui/Dialog/Dialog";
import { DeadlineMilestones, type CallDates } from "./DeadlineMilestones";
import { MatchScore } from "./MatchScore";
import { RecommendationEvidence, type RecommendationSubject } from "./RecommendationEvidence";
import { Fact, RiskDetails } from "./RiskDetails";
import { ScoreMeter } from "./ScoreMeter";
import { TopicTags } from "./TopicTags";
import { explainLabel } from "./paper";
import styles from "./Details.module.css";

export type EvidenceSection = "match" | "risk" | "deadline";

export interface EvidenceSubject {
  /** The paper's or call's title. */
  title: string;
  context: ExplanationContext;
  rank?: number | null;
  score?: number | null;
  scoreKind: "relevance" | "similarity" | "match";
  explanation: ExplanationSchema | null;
  sharedTopics?: string[];
  /** P6: a recommendation — "Why this match?" — explained from the recommendation API's own data. */
  recommendation?: RecommendationSubject;
  /** A call: its venue risk and its dates (venue matching, recommendations). */
  call?: {
    risk: RiskExplanation | null;
    riskLevel?: string | null;
    isPredatory?: boolean | null;
    deadline: OpportunityDeadline | null;
    dates: CallDates;
  };
}

interface EvidencePanelProps {
  subject: EvidenceSubject | null;
  onClose: () => void;
  /** Which part a trigger asked for; that heading takes focus when the panel opens. */
  section?: EvidenceSection;
  /** The ranking mode the API reports, for the technical details. */
  rankingMode?: string | null;
}

const signed = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(4)}`;

/**
 * "Why this result?" — the Evidence panel (FRONTEND_REDESIGN_PLAN.md §9, DESIGN_SYSTEM.md §9): a
 * Drawer named by the question, with the paper or call as its description. A summary in plain
 * words; a meter per signal that counted, with human names; the evidence the backend lists; the
 * quality facts; for a call, its venue risk and dates; and "Technical details" with the exact
 * score decomposition, unchanged, for examiners. Everything comes from the API's explanation;
 * nothing is added to it. One panel serves search, similar papers and venue matching.
 */
export function EvidencePanel({ subject, onClose, section = "match", rankingMode }: EvidencePanelProps) {
  const id = useId();
  const riskHeading = useRef<HTMLHeadingElement>(null);
  const deadlineHeading = useRef<HTMLHeadingElement>(null);
  const open = subject !== null;

  // A trigger that asked for one part (the risk badge, the deadline) lands on it. The drawer puts
  // focus on its title as it opens; its effect runs first (child before parent), this one after.
  useEffect(() => {
    if (!open) return;
    if (section === "risk") riskHeading.current?.focus();
    if (section === "deadline") deadlineHeading.current?.focus();
  }, [open, section]);

  if (!subject) return <Drawer open={false} onClose={onClose} title="" size="lg">{null}</Drawer>;

  const { explanation, context, call } = subject;
  const signals = countedSignals(explanation);
  const summary = explanation ? (plainSummary(explanation, subject.rank) ?? explanation.summary) : null;
  const evidence = explanation?.academic_evidence ?? null;
  const breakdown = explanation?.score_breakdown ?? null;
  const reranker = explanation?.reranker_explanation ?? null;
  const diversity = explanation?.diversity_explanation ?? null;
  const topics = subject.sharedTopics?.length ? subject.sharedTopics : (explanation?.topic_evidence?.shared_topic_names ?? []);

  return (
    <Drawer open onClose={onClose} title={explainLabel(context)} description={subject.title} size="lg" className="evidence-panel">
      <div className={styles.stack}>
        {subject.recommendation ? (
          <RecommendationEvidence subject={subject.recommendation} headingId={id} />
        ) : (
          <section className={styles.section} aria-labelledby={`${id}-match`}>
            <h3 id={`${id}-match`} tabIndex={-1} className={styles.sectionTitle}>
              {context === "venue" ? "How well it fits the paper" : context === "similar" ? "How similar it is" : "How well it matches"}
            </h3>
            <div className={styles.cluster}>
              <MatchScore score={subject.score} kind={subject.scoreKind} />
              {subject.rank ? <span className={styles.muted}>Ranked #{subject.rank}</span> : null}
            </div>
            {summary && <p className={styles.text}>{summary}</p>}
            {!explanation && <p className={styles.muted}>No explanation was returned for this item.</p>}

            {signals.length > 0 && (
              <div className={styles.meters} aria-label="What counted" role="group">
                {signals.map((signal) => (
                  <ScoreMeter
                    key={signal.signal_name}
                    name={signalName(signal.signal_name, context)}
                    score={signal.score}
                    assessment={assessmentWord(signal.qualitative_assessment)}
                    available={signal.is_available}
                    description={signalDescription(signal.signal_name, context)}
                  />
                ))}
              </div>
            )}

            {topics.length > 0 && (
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>{context === "search" ? "Topics shared with your search" : "Shared topics"}</h4>
                <TopicTags topics={topics} shared label="Shared topics" />
              </div>
            )}

            {explanation && explanation.strengths.length > 0 && (
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>Evidence</h4>
                <ol className={styles.list}>
                  {explanation.strengths.map((strength, i) => (
                    <li key={i}>{strength}</li>
                  ))}
                </ol>
              </div>
            )}
            {explanation && explanation.limitations.length > 0 && (
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>Limits of this match</h4>
                <ul className={styles.list}>
                  {explanation.limitations.map((limitation, i) => (
                    <li key={i}>{limitation}</li>
                  ))}
                </ul>
              </div>
            )}

            {evidence && context !== "venue" && (
              <div className={styles.group}>
                <h4 className={styles.groupTitle}>About the paper</h4>
                <dl className={styles.facts}>
                  <Fact term="Citations" value={citationsLabel(evidence.citation_count) ?? "Not known"} />
                  <Fact term="Open access" value={evidence.oa_status ? assessmentWord(evidence.oa_status) : evidence.is_in_doaj ? "Yes (DOAJ)" : "Not known"} />
                  {evidence.canonical_venue_name && <Fact term="Published in" value={evidence.canonical_venue_name} />}
                  {evidence.institution_names.length > 0 && <Fact term="Institutions" value={evidence.institution_names.join(", ")} />}
                </dl>
              </div>
            )}
          </section>
        )}

        {call && (
          <section className={styles.section} aria-labelledby={`${id}-risk`}>
            <h3 id={`${id}-risk`} ref={riskHeading} tabIndex={-1} className={styles.sectionTitle}>
              Venue risk
            </h3>
            <RiskDetails explanation={call.risk} level={call.riskLevel} isPredatory={call.isPredatory} />
          </section>
        )}

        {call && (
          <section className={styles.section} aria-labelledby={`${id}-deadline`}>
            <h3 id={`${id}-deadline`} ref={deadlineHeading} tabIndex={-1} className={styles.sectionTitle}>
              Deadlines
            </h3>
            <DeadlineMilestones intelligence={call.deadline} dates={call.dates} />
          </section>
        )}

        {explanation && !subject.recommendation && (
          <details className={styles.technical}>
            <summary>Technical details</summary>
            <div className={styles.technicalBody}>
              {explanation.summary && <p className={styles.text}>{explanation.summary}</p>}
              <dl className={styles.facts}>
                {rankingMode && <Fact term="Ranking mode" value={rankingMode} />}
                <Fact term="Final score" value={explanation.final_score.toFixed(4)} />
                {breakdown && (
                  <>
                    <Fact term="Relevance subtotal" value={signed(breakdown.relevance_subtotal)} />
                    <Fact term="Contextual subtotal" value={signed(breakdown.contextual_subtotal)} />
                    <Fact term="Academic subtotal" value={signed(breakdown.academic_subtotal)} />
                    <Fact term="Base score" value={breakdown.base_score.toFixed(4)} />
                    <Fact term="Reranker adjustment" value={signed(breakdown.reranker_adjustment)} />
                    <Fact term="Diversity adjustment" value={signed(breakdown.diversity_adjustment)} />
                    <Fact term="Reconciled" value={breakdown.is_reconciled ? "Yes" : `No (gap ${breakdown.reconciliation_gap.toFixed(4)})`} />
                  </>
                )}
                {(explanation.provenance_evidence?.retrieval_sources?.length ?? 0) > 0 && (
                  <Fact term="Found by" value={explanation.provenance_evidence.retrieval_sources.join(", ")} />
                )}
              </dl>
              {Object.keys(explanation.signal_contributions).length > 0 && (
                <div className="rc-scroll-x" role="region" aria-label="Signal contributions" tabIndex={0}>
                  <table className={styles.table}>
                    <caption>Signal contributions</caption>
                    <thead>
                      <tr>
                        <th scope="col">Signal</th>
                        <th scope="col">Score</th>
                        <th scope="col">Weight</th>
                        <th scope="col">Contribution</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.values(explanation.signal_contributions).map((signal) => (
                        <tr key={signal.signal_name}>
                          <th scope="row">{signal.signal_name}</th>
                          <td>{signal.score.toFixed(4)}</td>
                          <td>{signal.weight.toFixed(4)}</td>
                          <td>{signed(signal.contribution)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {reranker?.enabled && reranker.description && <p className={styles.muted}>Reranker: {reranker.description}</p>}
              {diversity?.enabled && diversity.description && <p className={styles.muted}>Diversity: {diversity.description}</p>}
              {explanation.provenance_evidence?.description && <p className={styles.muted}>{explanation.provenance_evidence.description}</p>}
            </div>
          </details>
        )}
      </div>
    </Drawer>
  );
}
