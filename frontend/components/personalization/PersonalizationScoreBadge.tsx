"use client";

import React, { useState } from "react";
import type { PersonalizationAssessment } from "../../types/personalization";

interface PersonalizationScoreBadgeProps {
  assessment: PersonalizationAssessment | null;
  showDetails?: boolean;
  className?: string;
}

export const PersonalizationScoreBadge: React.FC<PersonalizationScoreBadgeProps> = ({
  assessment,
  showDetails = true,
  className = "",
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!assessment) {
    return null;
  }

  const { score, breakdown, explanation } = assessment;
  const pct = Math.round(score.bounded_score * 100);
  const matchState = score.match_state;

  // Visual styling token selection
  let badgeLabel = `${pct}% Match`;
  let badgeBg = "rgba(59, 130, 246, 0.12)";
  let badgeColor = "#3b82f6";
  let badgeBorder = "rgba(59, 130, 246, 0.3)";
  let badgeIcon = "★";

  if (matchState === "EXCLUDED_MATCH") {
    badgeLabel = "Excluded Match";
    badgeBg = "rgba(239, 68, 68, 0.12)";
    badgeColor = "#ef4444";
    badgeBorder = "rgba(239, 68, 68, 0.3)";
    badgeIcon = "✕";
  } else if (matchState === "CONFLICT") {
    badgeLabel = `${pct}% Conflict`;
    badgeBg = "rgba(245, 158, 11, 0.15)";
    badgeColor = "#f59e0b";
    badgeBorder = "rgba(245, 158, 11, 0.4)";
    badgeIcon = "⚠";
  } else if (matchState === "NEUTRAL" && pct === 0) {
    badgeLabel = "Neutral (No Prefs)";
    badgeBg = "rgba(255, 255, 255, 0.05)";
    badgeColor = "#94a3b8";
    badgeBorder = "rgba(255, 255, 255, 0.1)";
    badgeIcon = "○";
  } else if (pct >= 70) {
    badgeLabel = `${pct}% High Match`;
    badgeBg = "rgba(16, 185, 129, 0.12)";
    badgeColor = "#10b981";
    badgeBorder = "rgba(16, 185, 129, 0.3)";
    badgeIcon = "✓";
  } else if (pct < 40) {
    badgeLabel = `${pct}% Low Match`;
    badgeBg = "rgba(148, 163, 184, 0.12)";
    badgeColor = "#94a3b8";
    badgeBorder = "rgba(148, 163, 184, 0.25)";
    badgeIcon = "◐";
  }

  return (
    <div className={`personalization-score-badge-container ${className}`} style={{ display: "inline-block", position: "relative" }}>
      <button
        type="button"
        onClick={() => showDetails && setIsExpanded(!isExpanded)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "4px 10px",
          borderRadius: "9999px",
          fontSize: "12px",
          fontWeight: 600,
          backgroundColor: badgeBg,
          color: badgeColor,
          border: `1px solid ${badgeBorder}`,
          cursor: showDetails ? "pointer" : "default",
          transition: "all 0.15s ease",
        }}
        title={explanation.summary}
      >
        <span style={{ fontWeight: "bold" }}>{badgeIcon}</span>
        <span>{badgeLabel}</span>
        {showDetails && (
          <span style={{ fontSize: "10px", opacity: 0.7, marginLeft: "2px" }}>
            {isExpanded ? "▲" : "▼"}
          </span>
        )}
      </button>

      {isExpanded && showDetails && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: "0",
            zIndex: 50,
            width: "360px",
            maxWidth: "90vw",
            backgroundColor: "#0f172a",
            border: "1px solid #334155",
            borderRadius: "8px",
            padding: "14px",
            boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)",
            fontSize: "12px",
            color: "#e2e8f0",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", borderBottom: "1px solid #1e293b", paddingBottom: "8px" }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: "13px", color: badgeColor }}>
                {pct}% Personalization Score
              </span>
              <span style={{ marginLeft: "8px", fontSize: "11px", color: "#94a3b8" }}>
                Confidence: {Math.round(score.confidence * 100)}%
              </span>
            </div>
            <button
              type="button"
              onClick={() => setIsExpanded(false)}
              style={{
                background: "none",
                border: "none",
                color: "#94a3b8",
                cursor: "pointer",
                fontSize: "14px",
                padding: "2px 6px",
              }}
            >
              ✕
            </button>
          </div>

          {/* Executive Summary */}
          <div style={{ marginBottom: "12px", color: "#cbd5e1", lineHeight: "1.4", fontStyle: "italic" }}>
            {explanation.summary}
          </div>

          {/* Positive Contributions */}
          {breakdown.positive_contributions.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#10b981", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Positive Signals (+{Math.round(score.positive_contribution * 100)}%)
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "#94a3b8" }}>
                {breakdown.positive_contributions.map((c, idx) => (
                  <li key={`pos-${idx}`} style={{ marginBottom: "2px" }}>
                    <span style={{ color: "#e2e8f0", fontWeight: 500 }}>
                      {c.dimension.replace("_", " ")}:
                    </span>{" "}
                    {c.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Negative Penalties / Exclusions */}
          {breakdown.negative_contributions.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Negative Signals (-{Math.round(score.negative_penalty * 100)}%)
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "#94a3b8" }}>
                {breakdown.negative_contributions.map((c, idx) => (
                  <li key={`neg-${idx}`} style={{ marginBottom: "2px" }}>
                    <span style={{ color: "#fca5a5", fontWeight: 500 }}>
                      {c.dimension.replace("_", " ")}:
                    </span>{" "}
                    {c.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Conflicting / Unresolved Signals */}
          {breakdown.unresolved_contributions.some((c) => c.match_type === "CONFLICT") && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#f59e0b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Preference Conflicts
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "#fde68a" }}>
                {breakdown.unresolved_contributions
                  .filter((c) => c.match_type === "CONFLICT")
                  .map((c, idx) => (
                    <li key={`conflict-${idx}`} style={{ marginBottom: "2px" }}>
                      {c.explanation}
                    </li>
                  ))}
              </ul>
            </div>
          )}

          {/* Insufficient Evidence */}
          {breakdown.unresolved_contributions.some((c) => c.match_type === "INSUFFICIENT_EVIDENCE") && (
            <div style={{ marginBottom: "6px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Missing Opportunity Data
              </div>
              <div style={{ color: "#94a3b8", fontSize: "11px" }}>
                {breakdown.unresolved_contributions
                  .filter((c) => c.match_type === "INSUFFICIENT_EVIDENCE")
                  .map((c) => c.dimension.replace("_", " ").toLowerCase())
                  .join(", ")}
              </div>
            </div>
          )}

          {/* Footer note */}
          <div style={{ marginTop: "10px", paddingTop: "8px", borderTop: "1px solid #1e293b", fontSize: "10px", color: "#64748b", textAlign: "right" }}>
            Deterministic Scoring · Zero ML/LLM
          </div>
        </div>
      )}
    </div>
  );
};
