import type React from "react";
import type { RiskEvidenceItem, RiskExplanation } from "../../types/opportunity";
import { humanizeEnum } from "../../utils/date";
import { riskPresentation } from "../../utils/risk";
import { RiskIndicator } from "./RiskIndicator";
import styles from "./Details.module.css";

/** One term and its value in a definition list (every pair in its own group, as HTML allows). */
export function Fact({ term, value }: { term: string; value: React.ReactNode }) {
  return (
    <div className={styles.factRow}>
      <dt>{term}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function EvidenceList({ title, items, Heading }: { title: string; items: RiskEvidenceItem[]; Heading: "h3" | "h4" }) {
  if (items.length === 0) return null;
  return (
    <div className={styles.group}>
      <Heading className={styles.groupTitle}>
        {title} ({items.length})
      </Heading>
      <ul className={styles.list}>
        {items.map((item, i) => (
          <li key={`${item.signal}-${i}`}>
            {item.explanation}
            {item.provenance && <span className={styles.source}> Source: {item.provenance}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A venue's risk assessment in words (DESIGN_SYSTEM.md §9 RiskIndicator, expanded): the level, the
 * backend's own summary and reasons, then the evidence it weighed — signs of trust, warning signs
 * and missing information (missing information is never a warning). The scores are behind
 * "Technical details". Without an explanation it says only what the level says.
 */
export function RiskDetails({
  explanation,
  level,
  isPredatory,
  headingLevel = 4,
}: {
  explanation: RiskExplanation | null;
  level?: string | null;
  isPredatory?: boolean | null;
  /** The level of its group headings: 4 inside the Evidence panel's h3 section, 3 under a page's h2. */
  headingLevel?: 3 | 4;
}) {
  const Heading = `h${headingLevel}` as "h3" | "h4";
  const shownLevel = explanation?.risk_level ?? level ?? null;
  const predatory = explanation?.is_predatory_flag ?? isPredatory ?? false;
  const presentation = riskPresentation(shownLevel, { isPredatory: predatory });

  return (
    <div className={styles.stack}>
      <div className={styles.lead}>
        <RiskIndicator level={shownLevel} isPredatory={predatory} />
        <p className={styles.text}>{presentation.description}</p>
      </div>
      {explanation && (
        <>
          {explanation.summary && <p className={styles.text}>{explanation.summary}</p>}
          {explanation.risk_reasons.length > 0 && (
            <ul className={styles.list}>
              {explanation.risk_reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
          <EvidenceList title="Signs of trust" items={explanation.positive_trust_signals} Heading={Heading} />
          <EvidenceList title="Warning signs" items={explanation.suspicious_signals} Heading={Heading} />
          <EvidenceList title="Missing information" items={explanation.neutral_signals} Heading={Heading} />
          {explanation.limitations.length > 0 && (
            <div className={styles.group}>
              <Heading className={styles.groupTitle}>Limits of this assessment</Heading>
              <ul className={styles.list}>
                {explanation.limitations.map((limitation, i) => (
                  <li key={i}>{limitation}</li>
                ))}
              </ul>
            </div>
          )}
          <details className={styles.technical}>
            <summary>Technical details</summary>
            <dl className={styles.facts}>
              <Fact term="Risk score" value={explanation.risk_score.toFixed(4)} />
              <Fact term="Confidence" value={explanation.risk_confidence.toFixed(2)} />
              <Fact term="Evidence" value={humanizeEnum(explanation.evidence_sufficiency)} />
              <Fact term="Warning signs (gross)" value={`+${explanation.gross_negative_score.toFixed(4)}`} />
              <Fact term="Trust deducted" value={`−${explanation.trust_mitigation_score.toFixed(4)}`} />
              {Object.entries(explanation.provenance_summary).map(([source, count]) => (
                <Fact key={source} term={`Signals from ${source}`} value={String(count)} />
              ))}
            </dl>
          </details>
        </>
      )}
    </div>
  );
}
