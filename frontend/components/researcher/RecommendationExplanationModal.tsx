"use client";

import React, { useState } from "react";
import type { RecommendationExplanation } from "../../types/researcher";
import {
  AlertTriangle,
  Award,
  BookmarkCheck,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  History,
  Info,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Button } from "../ui/Button/Button";
import { Dialog } from "../ui/Dialog/Dialog";

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


  const getStrengthBadge = (strength: string) => {
    switch (strength) {
      case "Highly personalized":
        return {
          bg: "var(--rc-brand-subtle)",
          color: "var(--rc-brand-text)",
          border: "var(--rc-brand-border)",
          icon: <Sparkles size={13} />,
        };
      case "Personalized":
        return {
          bg: "var(--rc-success-subtle)",
          color: "var(--rc-success)",
          border: "var(--rc-success-border)",
          icon: <TrendingUp size={13} />,
        };
      case "Some personalization":
        return {
          bg: "var(--rc-info-subtle)",
          color: "var(--rc-info)",
          border: "var(--rc-info-border)",
          icon: <Award size={13} />,
        };
      case "General recommendation":
      default:
        return {
          bg: "var(--rc-surface-sunken)",
          color: "var(--rc-text-secondary)",
          border: "var(--rc-border)",
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
    <Dialog
      open={isOpen}
      onClose={onClose}
      title={opportunityTitle || "Recommended opportunity"}
      description={
        <>
          {explanation?.is_historical ? "Why this was recommended" : "Why this is recommended"}
          {organization ? ` · ${organization}` : ""}
        </>
      }
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
        <div>
          {loading ? (
            <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
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
                    background: "var(--rc-bg)",
                    border: "1px solid var(--rc-border-strong)",
                    borderRadius: "8px",
                    fontSize: "12px",
                    color: "var(--rc-text-secondary)",
                  }}
                >
                  <History size={15} color="var(--rc-text-muted)" />
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
                  <span style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, letterSpacing: "0.04em" }}>
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
                    background: isHighRisk ? "var(--rc-danger-subtle)" : "var(--rc-success-subtle)",
                    border: `1px solid ${isHighRisk ? "var(--rc-danger-border)" : "var(--rc-success-border)"}`,
                    color: isHighRisk ? "var(--rc-danger)" : "var(--rc-success)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, letterSpacing: "0.04em" }}>
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
                    background: "var(--rc-bg)",
                    border: "1px solid var(--rc-border)",
                    color: "var(--rc-text-secondary)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <span style={{ fontSize: "var(--rc-text-label-size)", fontWeight: 700, letterSpacing: "0.04em", color: "var(--rc-text-muted)" }}>
                    Timeline
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", fontWeight: 600 }}>
                    <Calendar size={13} color="var(--rc-text-muted)" />
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
                    background: "var(--rc-danger-subtle)",
                    border: "1px solid var(--rc-danger-border)",
                    borderRadius: "8px",
                    color: "var(--rc-danger)",
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
                    letterSpacing: "0.04em",
                    color: "var(--text-muted)",
                  }}
                >
                  Top Matching Reasons
                </h4>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    background: "var(--bg-main)",
                    padding: "12px 16px",
                    borderRadius: "8px",
                    border: "1px solid var(--border-color)",
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
                          color: "var(--text-main)",
                        }}
                      >
                        <CheckCircle2
                          size={15}
                          color="var(--rc-success)"
                          style={{ flexShrink: 0, marginTop: "2px" }}
                        />
                        <span>{reason}</span>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                      Recommended based on general opportunity discovery and profile keyword alignment.
                    </div>
                  )}
                </div>
              </div>

              {/* Categorized Factors Breakdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {/* Explicit Preferences */}
                {explanation.preference_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid var(--rc-info)", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--rc-info)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <BookmarkCheck size={14} /> Explicit Preferences
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "var(--rc-text-secondary)" }}>
                      {explanation.preference_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Research Expertise & Interests */}
                {explanation.expertise_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid var(--rc-success)", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--rc-success)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <Award size={14} /> Research Expertise & Focus
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "var(--rc-text-secondary)" }}>
                      {explanation.expertise_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Behavioral Learning Signals */}
                {explanation.behavioral_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid var(--rc-brand)", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--rc-brand-text)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <TrendingUp size={14} /> Learned from Your Activity
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "var(--rc-text-secondary)" }}>
                      {explanation.behavioral_reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Negative Demotion Signals */}
                {explanation.negative_reasons.length > 0 && (
                  <div style={{ borderLeft: "3px solid var(--rc-danger)", paddingLeft: "12px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--rc-danger)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <TrendingDown size={14} /> Signals Lowering Ranking
                    </div>
                    <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "var(--rc-text-secondary)" }}>
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
                  border: "1px solid var(--border-color)",
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
                    background: "var(--bg-main)",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "var(--text-muted)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Info size={14} />
                    <span>Technical Score Breakdown & Transparency</span>
                  </div>
                  {showDiagnosticScores ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>

                {showDiagnosticScores && (
                  <div style={{ padding: "12px 14px", fontSize: "12px", background: "var(--bg-card)" }}>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(4, 1fr)",
                        gap: "8px",
                        textAlign: "center",
                        padding: "8px 0",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: "var(--rc-text-label-size)" }}>Base Relevance</div>
                        <div style={{ fontWeight: 700, fontFamily: "monospace", fontSize: "13px" }}>
                          {explanation.base_relevance_score.toFixed(3)}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: "var(--rc-text-label-size)" }}>Personalization</div>
                        <div
                          style={{
                            fontWeight: 700,
                            fontFamily: "monospace",
                            fontSize: "13px",
                            color: explanation.personalization_contribution >= 0 ? "var(--rc-success)" : "var(--rc-danger)",
                          }}
                        >
                          {explanation.personalization_contribution >= 0
                            ? `+${explanation.personalization_contribution.toFixed(3)}`
                            : explanation.personalization_contribution.toFixed(3)}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: "var(--rc-text-label-size)" }}>Final Rank</div>
                        <div style={{ fontWeight: 700, fontFamily: "monospace", fontSize: "13px" }}>
                          #{explanation.rank}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: "var(--rc-text-label-size)" }}>Final Score</div>
                        <div
                          style={{
                            fontWeight: 700,
                            fontFamily: "monospace",
                            fontSize: "13px",
                            color: "var(--primary)",
                          }}
                        >
                          {explanation.final_score.toFixed(3)}
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        marginTop: "8px",
                        fontSize: "var(--rc-text-label-size)",
                        color: "var(--text-muted)",
                        lineHeight: "1.4",
                      }}
                    >
                      Confidence: <strong>{explanation.confidence}</strong> (
                      {(explanation.confidence_score * 100).toFixed(0)}%). Your preferences can only adjust
                      the ranking within fixed limits.
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>
              No explanation available for this opportunity.
            </div>
          )}
        </div>

    </Dialog>
  );
}
