"use client";

import React, { useEffect, useState } from "react";
import type { RecommendationExplanation } from "../../types/researcher";
import {
  AlertTriangle,
  Award,
  BookmarkCheck,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  HelpCircle,
  History,
  Info,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";

interface RecommendationExplanationModalProps {
  isOpen: boolean;
  onClose: () => void;
  explanation: RecommendationExplanation | null;
  loading?: boolean;
  opportunityTitle?: string;
  organization?: string;
}

export function RecommendationExplanationModal({
  isOpen,
  onClose,
  explanation,
  loading = false,
  opportunityTitle,
  organization,
}: RecommendationExplanationModalProps) {
  const [showDiagnosticScores, setShowDiagnosticScores] = useState<boolean>(false);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getStrengthBadge = (strength: string) => {
    switch (strength) {
      case "Highly personalized":
        return {
          bg: "#eef2ff",
          color: "#4338ca",
          border: "#c7d2fe",
          icon: <Sparkles size={13} />,
        };
      case "Personalized":
        return {
          bg: "#ecfdf5",
          color: "#047857",
          border: "#a7f3d0",
          icon: <TrendingUp size={13} />,
        };
      case "Some personalization":
        return {
          bg: "#eff6ff",
          color: "#1d4ed8",
          border: "#bfdbfe",
          icon: <Award size={13} />,
        };
      case "General recommendation":
      default:
        return {
          bg: "#f3f4f6",
          color: "#4b5563",
          border: "#e5e7eb",
          icon: <Info size={13} />,
        };
    }
  };

  const strengthStyle = explanation
    ? getStrengthBadge(explanation.personalization_strength)
    : getStrengthBadge("General recommendation");

  const isHighRisk =
    explanation?.risk_summary?.toLowerCase().includes("risk") ||
    explanation?.trust_status?.toLowerCase().includes("risk");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="explanation-modal-title"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: "16px",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "var(--bg-card, #ffffff)",
          border: "1px solid var(--border-color, #e2e8f0)",
          borderRadius: "var(--radius-lg, 12px)",
          width: "100%",
          maxWidth: "680px",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border-color, #e2e8f0)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            background: "var(--bg-card-header, #f8fafc)",
          }}
        >
          <div style={{ flex: 1, paddingRight: "16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <HelpCircle size={18} color="var(--primary, #2563eb)" />
              <h3
                id="explanation-modal-title"
                style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-main, #0f172a)" }}
              >
                {explanation?.is_historical ? "Why Was This Recommended?" : "Why This Recommendation?"}
              </h3>
            </div>
            <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-main, #334155)", marginTop: "2px" }}>
              {opportunityTitle || `Opportunity ${explanation?.opportunity_id.slice(0, 8)}`}
            </div>
            {organization && (
              <div style={{ fontSize: "12px", color: "var(--text-muted, #64748b)" }}>
                {organization}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "6px",
              borderRadius: "6px",
              color: "var(--text-muted, #64748b)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1 }}>
          {loading ? (
            <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted, #64748b)" }}>
              <div style={{ marginBottom: "8px" }}>Loading ranking explanation...</div>
              <div style={{ fontSize: "12px" }}>Analyzing ground-truth personalization signals</div>
            </div>
          ) : explanation ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Snapshot / Historical Banner */}
              {explanation.is_historical && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "10px 14px",
                    background: "#f8fafc",
                    border: "1px solid #cbd5e1",
                    borderRadius: "8px",
                    fontSize: "12px",
                    color: "#475569",
                  }}
                >
                  <History size={15} color="#64748b" />
                  <div>
                    <strong>Historical Snapshot:</strong> Explaining point-in-time recommendation from{" "}
                    {new Date(explanation.generated_at).toLocaleDateString()} (Ranking v{explanation.ranking_version}).
                    Immutable record — not recomputed with current preferences.
                  </div>
                </div>
              )}

              {/* Status Row: Personalization Strength, Trust, Deadline */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: "10px",
                }}
              >
                {/* Personalization Strength */}
                <div
                  style={{
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: strengthStyle.bg,
                    border: `1px solid ${strengthStyle.border}`,
                    color: strengthStyle.color,
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "10px", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Personalization
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", fontWeight: 700 }}>
                    {strengthStyle.icon}
                    {explanation.personalization_strength}
                  </div>
                </div>

                {/* Trust & Safety Status */}
                <div
                  style={{
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: isHighRisk ? "#fef2f2" : "#f0fdf4",
                    border: `1px solid ${isHighRisk ? "#fecaca" : "#bbf7d0"}`,
                    color: isHighRisk ? "#991b1b" : "#166534",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "10px", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                    Trust & Safety
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", fontWeight: 700 }}>
                    {isHighRisk ? <ShieldAlert size={14} /> : <Shield size={14} />}
                    {explanation.trust_status || "Verified"}
                  </div>
                </div>

                {/* Deadline Context */}
                <div
                  style={{
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    color: "#334155",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "10px", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em", color: "#64748b" }}>
                    Timeline
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", fontWeight: 600 }}>
                    <Calendar size={13} color="#64748b" />
                    {explanation.deadline_summary || "Deadline recorded"}
                  </div>
                </div>
              </div>

              {/* Safety Dominance Alert (If Risk Detected) */}
              {isHighRisk && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    padding: "12px 14px",
                    background: "#fff1f2",
                    border: "1px solid #fda4af",
                    borderRadius: "8px",
                    color: "#9f1239",
                    fontSize: "13px",
                  }}
                >
                  <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
                  <div>
                    <strong>Risk Notice:</strong> {explanation.risk_summary || "Opportunity flagged for quality review."}{" "}
                    Personalization relevance does not override or endorse safety checks.
                  </div>
                </div>
              )}

              {/* Primary Explanation Reasons (Checkmark list) */}
              <div>
                <h4
                  style={{
                    margin: "0 0 8px 0",
                    fontSize: "13px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                    color: "var(--text-muted, #475569)",
                  }}
                >
                  Top Matching Reasons
                </h4>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    background: "var(--bg-main, #f8fafc)",
                    padding: "12px 16px",
                    borderRadius: "8px",
                    border: "1px solid var(--border-color, #e2e8f0)",
                  }}
                >
                  {explanation.primary_reasons.length > 0 ? (
                    explanation.primary_reasons.map((reason, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "8px",
                          fontSize: "13px",
                          lineHeight: "1.4",
                          color: "var(--text-main, #1e293b)",
                        }}
                      >
                        <CheckCircle2
                          size={15}
                          color="#059669"
                          style={{ flexShrink: 0, marginTop: "2px" }}
                        />
                        <span>{reason}</span>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
                      Recommended based on general opportunity discovery and profile keyword alignment.
                    </div>
                  )}
                </div>
              </div>

              {/* Categorized Factors Breakdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {/* Explicit Preferences */}
                {explanation.preference_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid #3b82f6", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#1d4ed8", display: "flex", alignItems: "center", gap: "6px" }}>
                      <BookmarkCheck size={14} /> Explicit Preferences
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#334155" }}>
                      {explanation.preference_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Research Expertise & Interests */}
                {explanation.expertise_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid #10b981", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#047857", display: "flex", alignItems: "center", gap: "6px" }}>
                      <Award size={14} /> Research Expertise & Focus
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#334155" }}>
                      {explanation.expertise_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Behavioral Learning Signals */}
                {explanation.behavioral_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid #8b5cf6", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#6d28d9", display: "flex", alignItems: "center", gap: "6px" }}>
                      <TrendingUp size={14} /> Learned from Your Activity
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#334155" }}>
                      {explanation.behavioral_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Negative Demotion Signals */}
                {explanation.negative_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid #ef4444", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#b91c1c", display: "flex", alignItems: "center", gap: "6px" }}>
                      <TrendingDown size={14} /> Signals Lowering Ranking
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#334155" }}>
                      {explanation.negative_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Developer / Diagnostic Score Breakdown (Collapsible) */}
              <div
                style={{
                  border: "1px solid var(--border-color, #e2e8f0)",
                  borderRadius: "8px",
                  overflow: "hidden",
                }}
              >
                <button
                  onClick={() => setShowDiagnosticScores(!showDiagnosticScores)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    background: "var(--bg-main, #f8fafc)",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "var(--text-muted, #475569)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Info size={14} />
                    <span>Technical Score Breakdown & Transparency</span>
                  </div>
                  {showDiagnosticScores ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>

                {showDiagnosticScores && (
                  <div style={{ padding: "12px 14px", fontSize: "12px", background: "var(--bg-card, #ffffff)" }}>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(4, 1fr)",
                        gap: "8px",
                        textAlign: "center",
                        padding: "8px 0",
                        borderBottom: "1px solid var(--border-color, #e2e8f0)",
                      }}
                    >
                      <div>
                        <div style={{ color: "var(--text-muted, #64748b)", fontSize: "11px" }}>Base Relevance</div>
                        <div style={{ fontWeight: 700, fontFamily: "monospace", fontSize: "13px" }}>
                          {explanation.base_relevance_score.toFixed(3)}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted, #64748b)", fontSize: "11px" }}>Personalization</div>
                        <div
                          style={{
                            fontWeight: 700,
                            fontFamily: "monospace",
                            fontSize: "13px",
                            color: explanation.personalization_contribution >= 0 ? "#16a34a" : "#dc2626",
                          }}
                        >
                          {explanation.personalization_contribution >= 0
                            ? `+${explanation.personalization_contribution.toFixed(3)}`
                            : explanation.personalization_contribution.toFixed(3)}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted, #64748b)", fontSize: "11px" }}>Final Rank</div>
                        <div style={{ fontWeight: 700, fontFamily: "monospace", fontSize: "13px" }}>
                          #{explanation.rank}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted, #64748b)", fontSize: "11px" }}>Final Score</div>
                        <div
                          style={{
                            fontWeight: 700,
                            fontFamily: "monospace",
                            fontSize: "13px",
                            color: "var(--primary, #2563eb)",
                          }}
                        >
                          {explanation.final_score.toFixed(3)}
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        marginTop: "8px",
                        fontSize: "11px",
                        color: "var(--text-muted, #64748b)",
                        lineHeight: "1.4",
                      }}
                    >
                      Confidence: <strong>{explanation.confidence}</strong> (
                      {(explanation.confidence_score * 100).toFixed(0)}%). Personalization adjustment strictly bounded
                      by Phase 3.5 ranking rules.
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted, #64748b)" }}>
              No explanation available for this opportunity.
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 24px",
            borderTop: "1px solid var(--border-color, #e2e8f0)",
            display: "flex",
            justifyContent: "flex-end",
            background: "var(--bg-card-header, #f8fafc)",
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: "7px 16px",
              fontSize: "13px",
              fontWeight: 600,
              borderRadius: "6px",
              border: "1px solid var(--border-color, #cbd5e1)",
              background: "var(--bg-card, #ffffff)",
              color: "var(--text-main, #334155)",
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
