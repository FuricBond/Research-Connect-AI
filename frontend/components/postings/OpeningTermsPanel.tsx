"use client";

import { Banknote, CalendarRange, Clock, ShieldCheck } from "lucide-react";
import type { OpeningTerms } from "../../types/posting";
import { COMMITMENT_TYPE_LABELS, COMPENSATION_TYPE_LABELS } from "../../types/posting";

/**
 * Renders the terms of a funded appointment (Phase 5.11).
 *
 * Returns nothing for supervisor-led categories, where there is no appointment to fund and an
 * empty terms block would only imply the information was withheld.
 */
export function OpeningTermsPanel({ terms }: { terms: OpeningTerms }) {
  if (!terms.is_structured_opening) return null;

  const amount =
    terms.compensation_amount !== null
      ? `${terms.compensation_currency ?? ""} ${terms.compensation_amount.toLocaleString()}`.trim() +
        (terms.compensation_period ? ` per ${terms.compensation_period.toLowerCase()}` : "")
      : null;

  return (
    <section className="posting-detail-section">
      <h2>Appointment terms</h2>
      <dl className="posting-detail-facts">
        <div className="posting-fact">
          <dt>
            <Banknote size={12} aria-hidden="true" /> Compensation
          </dt>
          <dd>
            {COMPENSATION_TYPE_LABELS[terms.compensation_type]}
            {amount ? ` · ${amount}` : ""}
          </dd>
        </div>
        {terms.commitment_type && (
          <div className="posting-fact">
            <dt>
              <Clock size={12} aria-hidden="true" /> Commitment
            </dt>
            <dd>
              {COMMITMENT_TYPE_LABELS[terms.commitment_type]}
              {terms.hours_per_week ? ` · ${terms.hours_per_week} h/week` : ""}
            </dd>
          </div>
        )}
        {!terms.commitment_type && terms.hours_per_week !== null && (
          <div className="posting-fact">
            <dt>
              <Clock size={12} aria-hidden="true" /> Hours
            </dt>
            <dd>{terms.hours_per_week} h/week</dd>
          </div>
        )}
        {terms.duration_months !== null && (
          <div className="posting-fact">
            <dt>
              <CalendarRange size={12} aria-hidden="true" /> Duration
            </dt>
            <dd>
              {terms.duration_months} month{terms.duration_months === 1 ? "" : "s"}
            </dd>
          </div>
        )}
        <div className="posting-fact">
          <dt>
            <ShieldCheck size={12} aria-hidden="true" /> Applications
          </dt>
          <dd>{terms.accepts_applications ? "Handled on this platform" : "Contact the author directly"}</dd>
        </div>
      </dl>

      {terms.eligibility_requirements && (
        <>
          <h2 style={{ marginTop: "0.9rem" }}>Eligibility</h2>
          <p className="posting-detail-body">{terms.eligibility_requirements}</p>
        </>
      )}
    </section>
  );
}
