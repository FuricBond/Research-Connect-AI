import React from "react";
import { AlertTriangle, AlertCircle } from "lucide-react";

interface RiskWarningProps {
  isPredatory?: boolean | null;
  riskScore?: number | null;
  riskReasons?: string[] | null;
}

export const RiskWarning: React.FC<RiskWarningProps> = ({
  isPredatory,
  riskScore,
  riskReasons,
}) => {
  const numericRisk = typeof riskScore === "number" ? riskScore : 0.0;
  const isHighRisk = Boolean(isPredatory) || numericRisk >= 0.70;
  const isMediumRisk = !isHighRisk && numericRisk > 0.30;
  const reasons = Array.isArray(riskReasons) ? riskReasons : [];

  if (isHighRisk) {
    return (
      <div className="risk-warning-banner high-risk" role="alert">
        <div className="risk-warning-header">
          <AlertTriangle size={18} className="risk-icon" />
          <strong>Potential Predatory Publication Risk</strong>
          <span className="risk-badge">Penalized in Ranking (-80%)</span>
        </div>
        <p className="risk-description">
          This venue has been flagged for questionable editorial integrity or substandard review transparency.
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
          <span>Elevated Venue Risk Score ({(numericRisk * 100).toFixed(0)}%)</span>
        </div>
        {reasons.length > 0 && (
          <p className="risk-reasons-inline">{reasons.join(" • ")}</p>
        )}
      </div>
    );
  }

  return null;
};
