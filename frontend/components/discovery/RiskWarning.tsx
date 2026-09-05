"use client";

import React from "react";
import { AlertTriangle, AlertCircle, HelpCircle, ShieldCheck, ChevronRight } from "lucide-react";

interface RiskWarningProps {
  isPredatory?: boolean | null;
  riskScore?: number | null;
  riskReasons?: string[] | null;
  riskLevel?: string | null;
  riskConfidence?: number | null;
  onViewRiskDetails?: () => void;
}

export const RiskWarning: React.FC<RiskWarningProps> = ({
  isPredatory,
  riskScore,
  riskReasons,
  riskLevel,
  riskConfidence,
  onViewRiskDetails,
}) => {
  const numericRisk = typeof riskScore === "number" ? riskScore : 0.0;
  const isHighRisk =
    riskLevel === "HIGH_RISK" || Boolean(isPredatory) || numericRisk >= 0.70;
  const isMediumRisk =
    !isHighRisk && (riskLevel === "MODERATE_RISK" || numericRisk > 0.30);
  const isInsufficient =
    riskLevel === "INSUFFICIENT_EVIDENCE" ||
    (riskLevel === undefined && numericRisk === 0.0 && riskConfidence !== undefined && riskConfidence !== null && riskConfidence < 0.35);

  const reasons = Array.isArray(riskReasons) ? riskReasons : [];

  if (isHighRisk) {
    return (
      <div className="risk-warning-banner high-risk" role="alert">
        <div className="risk-warning-header">
          <AlertTriangle size={18} className="risk-icon" />
          <strong>Potential Publication Integrity Risk</strong>
          <span className="risk-badge">Penalized in Ranking (-80%)</span>
          {onViewRiskDetails && (
            <button
              type="button"
              className="risk-action-btn risk-action-high"
              onClick={onViewRiskDetails}
              title="Inspect corroborated risk evidence and provenance"
            >
              <span>Why? Inspect Evidence</span>
              <ChevronRight size={13} />
            </button>
          )}
        </div>
        <p className="risk-description">
          This venue has received a high risk assessment based on multiple corroborated suspicious indicators.
        </p>
        {reasons.length > 0 && (
          <ul className="risk-reasons-list">
            {reasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (isMediumRisk) {
    return (
      <div className="risk-warning-banner medium-risk" role="status">
        <div className="risk-warning-header">
          <AlertCircle size={16} className="risk-icon" />
          <span>Elevated Cautionary Risk Score ({(numericRisk * 100).toFixed(0)}%)</span>
          {onViewRiskDetails && (
            <button
              type="button"
              className="risk-action-btn risk-action-medium"
              onClick={onViewRiskDetails}
              title="Inspect cautionary indicators and trust mitigation"
            >
              <span>Inspect Evidence</span>
              <ChevronRight size={13} />
            </button>
          )}
        </div>
        {reasons.length > 0 && (
          <p className="risk-reasons-inline">{reasons.join(" • ")}</p>
        )}
      </div>
    );
  }

  if (isInsufficient) {
    return (
      <div className="risk-warning-banner neutral-risk" role="status">
        <div className="risk-warning-header">
          <HelpCircle size={15} className="risk-icon" />
          <span className="neutral-title">Limited Metadata Available (Neutral Assessment)</span>
          {onViewRiskDetails && (
            <button
              type="button"
              className="risk-action-btn risk-action-neutral"
              onClick={onViewRiskDetails}
              title="View metadata completeness and sufficiency details"
            >
              <span>Details</span>
              <ChevronRight size={13} />
            </button>
          )}
        </div>
        <p className="risk-description neutral-text">
          Insufficient evidence to establish verified trust or elevated risk. Missing data is strictly neutral and does not indicate predatory behavior.
        </p>
      </div>
    );
  }

  return null;
};

