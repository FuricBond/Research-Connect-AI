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
      bg: "rgba(16, 185, 129, 0.12)",
      text: "#10b981",
      border: "rgba(16, 185, 129, 0.3)",
      icon: "✓",
    },
    EXCLUDED_MATCH: {
      label: "Excluded by your preferences",
      bg: "rgba(239, 68, 68, 0.12)",
      text: "#ef4444",
      border: "rgba(239, 68, 68, 0.3)",
      icon: "✕",
    },
    CONFLICT: {
      label: "Preference conflict",
      bg: "rgba(245, 158, 11, 0.15)",
      text: "#f59e0b",
      border: "rgba(245, 158, 11, 0.4)",
      icon: "⚠",
    },
    PARTIAL_MATCH: {
      label: "Partial preference match",
      bg: "rgba(59, 130, 246, 0.12)",
      text: "#3b82f6",
      border: "rgba(59, 130, 246, 0.3)",
      icon: "◐",
    },
    INSUFFICIENT_EVIDENCE: {
      label: "Insufficient preference evidence",
      bg: "rgba(107, 114, 128, 0.12)",
      text: "#9ca3af",
      border: "rgba(107, 114, 128, 0.25)",
      icon: "?",
    },
    NEUTRAL: {
      label: "Neutral preference",
      bg: "rgba(255, 255, 255, 0.05)",
      text: "#94a3b8",
      border: "rgba(255, 255, 255, 0.1)",
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
          <span style={{ fontSize: "10px", opacity: 0.7, marginLeft: "2px" }}>
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
            backgroundColor: "#1e293b",
            border: "1px solid rgba(255, 255, 255, 0.12)",
            borderRadius: "8px",
            boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
            padding: "12px",
            fontSize: "12px",
            color: "#e2e8f0",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: "6px", color: current.text }}>
            {assessment.deterministic_explanation}
          </div>

          {/* Positive Matches */}
          {assessment.positive_matches.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#10b981", textTransform: "uppercase" }}>
                Preferred Matches ({assessment.positive_matches.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "#cbd5e1" }}>
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
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#ef4444", textTransform: "uppercase" }}>
                Explicit Exclusions ({assessment.excluded_matches.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "#fca5a5" }}>
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
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#f59e0b", textTransform: "uppercase" }}>
                Conflicts ({assessment.conflicts.length})
              </div>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "#fcd34d" }}>
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
            <div style={{ marginTop: "8px", fontSize: "11px", color: "#94a3b8" }}>
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
