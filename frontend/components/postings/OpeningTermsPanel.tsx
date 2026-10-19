"use client";

import type { OpeningTerms } from "../../types/posting";
import { COMMITMENT_TYPE_LABELS, COMPENSATION_TYPE_LABELS } from "../../types/posting";
import { COMPENSATION_PERIODS } from "./postingForm";
import styles from "./Faculty.module.css";

/**
 * Renders the terms of a funded appointment (Phase 5.11; P9 moved it to the design system).
 *
 * Returns nothing for supervisor-led categories, where there is no appointment to fund and an
 * empty terms block would only imply the information was withheld.
 */
export function OpeningTermsPanel({ terms }: { terms: OpeningTerms }) {
  if (!terms.is_structured_opening) return null;

  const period = COMPENSATION_PERIODS.find((item) => item.value === terms.compensation_period)?.label.toLowerCase() ?? null;
  const amount =
    terms.compensation_amount !== null
      ? `${terms.compensation_currency ?? ""} ${terms.compensation_amount.toLocaleString()}`.trim() + (period ? (period === "in total" ? " in total" : ` per ${period}`) : "")
      : null;

  return (
    <section className={styles.detailSection} aria-labelledby="posting-terms">
      <h2 id="posting-terms" className={styles.detailTitle}>
        Appointment terms
      </h2>
      <dl className={styles.factList}>
        <div>
          <dt>Compensation</dt>
          <dd>
            {COMPENSATION_TYPE_LABELS[terms.compensation_type]}
            {amount ? ` · ${amount}` : ""}
          </dd>
        </div>
        {terms.commitment_type && (
          <div>
            <dt>Commitment</dt>
            <dd>
              {COMMITMENT_TYPE_LABELS[terms.commitment_type]}
              {terms.hours_per_week ? ` · ${terms.hours_per_week} hours a week` : ""}
            </dd>
          </div>
        )}
        {!terms.commitment_type && terms.hours_per_week !== null && (
          <div>
            <dt>Hours</dt>
            <dd>{terms.hours_per_week} hours a week</dd>
          </div>
        )}
        {terms.duration_months !== null && (
          <div>
            <dt>Duration</dt>
            <dd>
              {terms.duration_months} month{terms.duration_months === 1 ? "" : "s"}
            </dd>
          </div>
        )}
        <div>
          <dt>Applications</dt>
          <dd>{terms.accepts_applications ? "Handled on this platform" : "Contact the author directly"}</dd>
        </div>
      </dl>

      {terms.eligibility_requirements && (
        <>
          <h3 className={styles.subTitle}>Eligibility</h3>
          <p className={styles.body}>{terms.eligibility_requirements}</p>
        </>
      )}
    </section>
  );
}
