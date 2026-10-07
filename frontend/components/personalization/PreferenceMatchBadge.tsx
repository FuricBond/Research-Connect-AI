"use client";

import React, { useState } from "react";
import type {
  PreferenceMatchType,
  PreferencePersonalizationAssessment,
} from "../../types/personalization";

interface PreferenceMatchBadgeProps {
  assessment: PreferencePersonalizationAssessment | null;
  matchType?: PreferenceMatchType;
  showDetails?: boolean;
  className?: string;
}

export const PreferenceMatchBadge: React.FC<PreferenceMatchBadgeProps> = ({
  assessment,
  matchType: propMatchType,
  showDetails = true,
  className = "",
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const state = propMatchType ?? assessment?.overall_match_state ?? "NEUTRAL";

  const config: Record<
    PreferenceMatchType,
    { label: string; bg: string; text: string; border: string; icon: string }
  > = {
    PREFERRED_MATCH: {
      label: "Matches your preferences",
      bg: "color-mix(in srgb, var(--rc-success) 12%, transparent)",
      text: "var(--rc-success)",
      border: "color-mix(in srgb, var(--rc-success) 30%, transparent)",
      icon: "✓",
    },
    EXCLUDED_MATCH: {
      label: "Excluded by your preferences",
      bg: "color-mix(in srgb, var(--rc-danger) 12%, transparent)",
      text: "var(--rc-danger)",
      border: "color-mix(in srgb, var(--rc-danger) 30%, transparent)",
      icon: "✕",
    },
    CONFLICT: {
      label: "Preference conflict",
      bg: "color-mix(in srgb, var(--rc-warning) 15%, transparent)",
      text: "var(--rc-warning)",
      border: "color-mix(in srgb, var(--rc-warning) 40%, transparent)",
      icon: "⚠",
    },
    PARTIAL_MATCH: {
      label: "Partial preference match",
      bg: "color-mix(in srgb, var(--rc-info) 12%, transparent)",
      text: "var(--rc-info)",
      border: "color-mix(in srgb, var(--rc-info) 30%, transparent)",
      icon: "◐",
    },
    INSUFFICIENT_EVIDENCE: {
      label: "Insufficient preference evidence",
      bg: "color-mix(in srgb, var(--rc-text-muted) 12%, transparent)",
      text: "var(--rc-text-muted)",
      border: "color-mix(in srgb, var(--rc-text-muted) 25%, transparent)",
      icon: "?",
    },
    NEUTRAL: {
      label: "Neutral preference",
      bg: "var(--rc-hover)",
      text: "var(--rc-text-muted)",
      border: "var(--rc-hover)",
      icon: "○",
    },
  };

  const current = config[state] || config.NEUTRAL;

  return (
    <div className={`preference-match-badge-container ${className}`} style={{ display: "inline-block" }}>
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
          backgroundColor: current.bg,
          color: current.text,
          border: `1px solid ${current.border}`,
          cursor: showDetails && assessment ? "pointer" : "default",
          transition: "all 0.15s ease",
        }}
        title={assessment?.deterministic_explanation || current.label}
      >
        <span style={{ fontWeight: "bold" }}>{current.icon}</span>
        <span>{current.label}</span>
        {showDetails && assessment && (
          <span style={{ fontSize: "var(--rc-text-label-size)", opacity: 0.7, marginLeft: "2px" }}>
            {isExpanded ? "▲" : "▼"}
          </span>
        )}
      </button>

      {showDetails && isExpanded && assessment && (
        <div
          style={{
            position: "absolute",
            zIndex: 40,
            marginTop: "6px",
            width: "320px",
            backgroundColor: "var(--rc-surface-inverse)",
            border: "1px solid var(--rc-hover)",
            borderRadius: "8px",
            boxShadow: "var(--rc-shadow-dialog)",
            padding: "12px",
            fontSize: "12px",
            color: "var(--rc-text)",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: "6px", color: current.text }}>
            {assessment.deterministic_explanation}
          </div>

          {/* Positive Matches */}
          {assessment.positive_matches.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-success)", }}>
                Preferred Matches ({assessment.positive_matches.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "var(--rc-text)" }}>
                {assessment.positive_matches.map((s) => (
                  <li key={s.signal_id} style={{ marginBottom: "2px" }}>
                    {s.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Excluded Matches */}
          {assessment.excluded_matches.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-danger)", }}>
                Explicit Exclusions ({assessment.excluded_matches.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "var(--rc-danger)" }}>
                {assessment.excluded_matches.map((s) => (
                  <li key={s.signal_id} style={{ marginBottom: "2px" }}>
                    {s.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Conflicts */}
          {assessment.conflicts.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, color: "var(--rc-warning)", }}>
                Conflicts ({assessment.conflicts.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "var(--rc-warning)" }}>
                {assessment.conflicts.map((s) => (
                  <li key={s.signal_id} style={{ marginBottom: "2px" }}>
                    {s.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Missing Evidence */}
          {assessment.insufficient_evidence_dimensions.length > 0 && (
            <div style={{ marginTop: "8px", fontSize: "var(--rc-text-label-size)", color: "var(--rc-text-muted)" }}>
              <span style={{ fontWeight: 600 }}>Unavailable Data:</span>{" "}
              {assessment.insufficient_evidence_dimensions
                .map((d) => d.replace("_", " ").toLowerCase())
                .join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
