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
  let badgeBg = "color-mix(in srgb, var(--rc-info) 12%, transparent)";
  let badgeColor = "var(--rc-info)";
  let badgeBorder = "color-mix(in srgb, var(--rc-info) 30%, transparent)";
  let badgeIcon = "★";

  if (matchState === "EXCLUDED_MATCH") {
    badgeLabel = "Excluded Match";
    badgeBg = "color-mix(in srgb, var(--rc-danger) 12%, transparent)";
    badgeColor = "var(--rc-danger)";
    badgeBorder = "color-mix(in srgb, var(--rc-danger) 30%, transparent)";
    badgeIcon = "✕";
  } else if (matchState === "CONFLICT") {
    badgeLabel = `${pct}% Conflict`;
    badgeBg = "color-mix(in srgb, var(--rc-warning) 15%, transparent)";
    badgeColor = "var(--rc-warning)";
    badgeBorder = "color-mix(in srgb, var(--rc-warning) 40%, transparent)";
    badgeIcon = "⚠";
  } else if (matchState === "NEUTRAL" && pct === 0) {
    badgeLabel = "Neutral (No Prefs)";
    badgeBg = "var(--rc-hover)";
    badgeColor = "var(--rc-text-muted)";
    badgeBorder = "var(--rc-hover)";
    badgeIcon = "○";
  } else if (pct >= 70) {
    badgeLabel = `${pct}% High Match`;
    badgeBg = "color-mix(in srgb, var(--rc-success) 12%, transparent)";
    badgeColor = "var(--rc-success)";
    badgeBorder = "color-mix(in srgb, var(--rc-success) 30%, transparent)";
    badgeIcon = "✓";
  } else if (pct < 40) {
    badgeLabel = `${pct}% Low Match`;
    badgeBg = "color-mix(in srgb, var(--rc-text-muted) 12%, transparent)";
    badgeColor = "var(--rc-text-muted)";
    badgeBorder = "color-mix(in srgb, var(--rc-text-muted) 25%, transparent)";
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
          <span style={{ fontSize: "var(--rc-text-label-size)", opacity: 0.7, marginLeft: "2px" }}>
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
            backgroundColor: "var(--rc-surface-inverse)",
            border: "1px solid var(--rc-border-control)",
            borderRadius: "8px",
            padding: "14px",
            boxShadow: "var(--rc-shadow-dialog)",
            fontSize: "12px",
            color: "var(--rc-text)",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", borderBottom: "1px solid var(--rc-border-control)", paddingBottom: "8px" }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: "13px", color: badgeColor }}>
                {pct}% Personalization Score
              </span>
              <span style={{ marginLeft: "8px", fontSize: "var(--rc-text-label-size)", color: "var(--rc-text-muted)" }}>
                Confidence: {Math.round(score.confidence * 100)}%
              </span>
            </div>
            <button
              type="button"
              onClick={() => setIsExpanded(false)}
              style={{
                background: "none",
                border: "none",
                color: "var(--rc-text-muted)",
                cursor: "pointer",
                fontSize: "14px",
                padding: "2px 6px",
              }}
            >
              ✕
            </button>
          </div>

          {/* Executive Summary */}
          <div style={{ marginBottom: "12px", color: "var(--rc-text)", lineHeight: "1.4", fontStyle: "italic" }}>
            {explanation.summary}
          </div>

          {/* Positive Contributions */}
          {breakdown.positive_contributions.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-success)", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Positive Signals (+{Math.round(score.positive_contribution * 100)}%)
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "var(--rc-text-muted)" }}>
                {breakdown.positive_contributions.map((c, idx) => (
                  <li key={`pos-${idx}`} style={{ marginBottom: "2px" }}>
                    <span style={{ color: "var(--rc-text)", fontWeight: 500 }}>
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
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-danger)", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Negative Signals (-{Math.round(score.negative_penalty * 100)}%)
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "var(--rc-text-muted)" }}>
                {breakdown.negative_contributions.map((c, idx) => (
                  <li key={`neg-${idx}`} style={{ marginBottom: "2px" }}>
                    <span style={{ color: "var(--rc-danger)", fontWeight: 500 }}>
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
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-warning)", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Preference Conflicts
              </div>
              <ul style={{ margin: "0", paddingLeft: "16px", color: "var(--rc-warning)" }}>
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
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-text-muted)", letterSpacing: "0.05em", marginBottom: "4px" }}>
                Missing Opportunity Data
              </div>
              <div style={{ color: "var(--rc-text-muted)", fontSize: "var(--rc-text-label-size)" }}>
                {breakdown.unresolved_contributions
                  .filter((c) => c.match_type === "INSUFFICIENT_EVIDENCE")
                  .map((c) => c.dimension.replace("_", " ").toLowerCase())
                  .join(", ")}
              </div>
            </div>
          )}

          {/* Footer note */}
          <div style={{ marginTop: "10px", paddingTop: "8px", borderTop: "1px solid var(--rc-border-control)", fontSize: "var(--rc-text-label-size)", color: "var(--rc-text-muted)", textAlign: "right" }}>
            Deterministic Scoring · Zero ML/LLM
          </div>
        </div>
      )}
    </div>
  );
};
