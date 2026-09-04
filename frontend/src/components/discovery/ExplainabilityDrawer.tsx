import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Award,
  CheckCircle2,
  Cpu,
  Database,
  HelpCircle,
  Info,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Shuffle,
  Sparkles,
  Tag,
  X,
} from "lucide-react";
import type { ExplanationSchema } from "../../types/discovery";
import type { RiskExplanation } from "../../types/opportunity";

interface ExplainabilityDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  explanation: ExplanationSchema | null;
  entityTitle: string;
  entityType?: "research_work" | "opportunity";
  riskExplanation?: RiskExplanation | null;
  initialTab?: "match" | "risk";
}

const SIGNAL_LABELS: Record<string, string> = {
  semantic_similarity: "Semantic Relevance",
  topic_similarity: "Canonical Topic Overlap",
  lexical_similarity: "Keyword / Lexical Match",
  type_compatibility: "Publication Type Compatibility",
  opportunity_quality: "Venue Indexing & Quality",
  urgency: "Deadline Proximity / Urgency",
  freshness: "Publication Recency",
  citation_impact: "Citation Impact",
  author_prominence: "Author Prominence (h-index)",
  author_position: "Author Lead Position",
  institution_prestige: "Institutional Prestige",
  venue_prestige: "Venue Prestige & Quality",
  open_access_tier: "Open Access Availability",
};

export const ExplainabilityDrawer: React.FC<ExplainabilityDrawerProps> = ({
  isOpen,
  onClose,
  explanation,
  entityTitle,
  entityType = "research_work",
  riskExplanation,
  initialTab = "match",
}) => {
  const [activeTab, setActiveTab] = useState<"match" | "risk">("match");

  // Sync initial tab when drawer opens
  useEffect(() => {
    if (isOpen) {
      if (initialTab === "risk" || (!explanation && riskExplanation)) {
        setActiveTab("risk");
      } else {
        setActiveTab("match");
      }
    }
  }, [isOpen, initialTab, explanation, riskExplanation]);

  // Handle ESC key to close drawer
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

  const contributions = Object.values(explanation?.signal_contributions || {});
  const totalContribution = contributions.reduce((sum, c) => sum + c.contribution, 0) || 1.0;
  const sb = explanation?.score_breakdown;
  const ae = explanation?.academic_evidence;
  const re = explanation?.reranker_explanation;
  const de = explanation?.diversity_explanation;

  const hasRisk = Boolean(riskExplanation);
  const isOpp = entityType === "opportunity" || hasRisk;

  return (
    <div className="drawer-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="drawer-content"
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {/* Drawer Header */}
        <div className="drawer-header">
          <div>
            <div className="drawer-eyebrow">
              <Sparkles size={14} />
              <span>
                {activeTab === "risk"
                  ? "Trust & Publication Integrity (Phase 2.6F)"
                  : "Ranking Explainability & Evidence (Phase 2.5F)"}
              </span>
            </div>
            <h2 className="drawer-title" title={entityTitle}>
              {entityTitle}
            </h2>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close explainability drawer"
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Navigation (for opportunities with trust/risk data) */}
        {isOpp && hasRisk && (
          <div className="drawer-tabs-bar" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "match"}
              className={`drawer-tab-btn ${activeTab === "match" ? "active" : ""}`}
              onClick={() => setActiveTab("match")}
            >
              <Sparkles size={14} />
              <span>Matching Relevance</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "risk"}
              className={`drawer-tab-btn ${activeTab === "risk" ? "active" : ""}`}
              onClick={() => setActiveTab("risk")}
            >
              {riskExplanation?.risk_level === "HIGH_RISK" ? (
                <ShieldAlert size={14} className="tab-icon-high" />
              ) : riskExplanation?.risk_level === "MODERATE_RISK" ? (
                <AlertCircle size={14} className="tab-icon-med" />
              ) : (
                <ShieldCheck size={14} className="tab-icon-low" />
              )}
              <span>Trust & Publication Safety</span>
              <span className={`drawer-tab-badge ${riskExplanation?.risk_level.toLowerCase()}`}>
                {riskExplanation?.risk_level.replace(/_/g, " ")}
              </span>
            </button>
          </div>
        )}

        <div className="drawer-body">
          {/* TAB 1: MATCHING RELEVANCE (Phase 2.5) */}
          {activeTab === "match" && explanation && (
            <>
              {/* Score & Rank Overview Card */}
              <div className="drawer-metric-card">
                <div className="metric-item">
                  <span className="metric-label">Composite Rank</span>
                  <span className="metric-value">#{explanation.rank}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Composite Score</span>
                  <span className="metric-value">
                    {(explanation.final_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Verification</span>
                  {sb?.is_reconciled ? (
                    <span className="math-verified-badge">
                      <ShieldCheck size={12} /> Math Verified
                    </span>
                  ) : (
                    <span className="math-verified-badge gap-warning">
                      <AlertCircle size={12} /> Gap: {sb?.reconciliation_gap.toFixed(4) || "0.0000"}
                    </span>
                  )}
                </div>
              </div>

              {/* Natural Language Summary */}
              <section className="drawer-section">
                <h3 className="section-title">
                  <HelpCircle size={16} />
                  <span>Why This {entityType === "opportunity" ? "Opportunity" : "Paper"} Was Ranked Here</span>
                </h3>
                <p className="explanation-summary">{explanation.summary}</p>
              </section>

              {/* Primary Drivers */}
              {explanation.primary_factors.length > 0 && (
                <section className="drawer-section">
                  <h4 className="subsection-title">Primary Ranking Drivers</h4>
                  <div className="primary-drivers-list">
                    {explanation.primary_factors.map((factor) => (
                      <span key={factor} className="driver-chip">
                        <Sparkles size={12} />
                        <span>{SIGNAL_LABELS[factor] || factor.replace(/_/g, " ")}</span>
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Exact Score Decomposition (Phase 2.5F) */}
              {sb && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Scale size={16} />
                    <span>Exact Score Decomposition</span>
                  </h3>
                  <div className="score-breakdown-card">
                    <div className="subtotals-grid">
                      <div className="subtotal-item">
                        <span className="subtotal-label">Relevance Subtotal</span>
                        <span className="subtotal-val">+{sb.relevance_subtotal.toFixed(4)}</span>
                      </div>
                      <div className="subtotal-item">
                        <span className="subtotal-label">Contextual Subtotal</span>
                        <span className="subtotal-val">+{sb.contextual_subtotal.toFixed(4)}</span>
                      </div>
                      <div className="subtotal-item">
                        <span className="subtotal-label">Academic Subtotal</span>
                        <span className="subtotal-val">+{sb.academic_subtotal.toFixed(4)}</span>
                      </div>
                    </div>

                    <div className="adjustments-row">
                      <span>Base Score: <strong>{sb.base_score.toFixed(4)}</strong></span>
                      {sb.reranker_adjustment !== 0 && (
                        <span className={`adjustment-badge ${sb.reranker_adjustment > 0 ? "positive" : "negative"}`}>
                          Neural Rerank: {sb.reranker_adjustment > 0 ? "+" : ""}{sb.reranker_adjustment.toFixed(4)}
                        </span>
                      )}
                      {sb.diversity_adjustment !== 0 && (
                        <span className={`adjustment-badge ${sb.diversity_adjustment > 0 ? "positive" : "negative"}`}>
                          Diversity/Novelty: {sb.diversity_adjustment > 0 ? "+" : ""}{sb.diversity_adjustment.toFixed(4)}
                        </span>
                      )}
                      <span>= Final Score: <strong>{sb.final_score.toFixed(4)}</strong></span>
                    </div>
                  </div>
                </section>
              )}

              {/* Academic Quality & Bibliographic Evidence (Phase 2.5D) */}
              {ae && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Award size={16} />
                    <span>Academic Quality Evidence</span>
                  </h3>
                  <div className="evidence-card">
                    <div className="evidence-grid">
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Citations</span>
                        <span className="evidence-stat-value">
                          {ae.citation_count !== null && ae.citation_count !== undefined
                            ? `${ae.citation_count.toLocaleString()} citations`
                            : "Unspecified"}
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Author Prominence</span>
                        <span className="evidence-stat-value">
                          {(ae.author_prominence_score * 100).toFixed(0)}% (h-index proxy)
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Lead Author Role</span>
                        <span className="evidence-stat-value">
                          {ae.author_position || "Contributing author"}
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Open Access</span>
                        <span className="evidence-stat-value">
                          {ae.oa_status ? ae.oa_status.toUpperCase() : ae.open_access_tier_score > 0.35 ? "Open Access" : "Standard"}
                        </span>
                      </div>
                    </div>

                    {ae.canonical_venue_name && (
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Publication Venue</span>
                        <span className="evidence-stat-value">{ae.canonical_venue_name}</span>
                      </div>
                    )}

                    {ae.institution_names && ae.institution_names.length > 0 && (
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Affiliations</span>
                        <span className="evidence-stat-value">{ae.institution_names.join(", ")}</span>
                      </div>
                    )}

                    {ae.description && (
                      <p className="topic-evidence-desc" style={{ marginTop: "4px" }}>
                        {ae.description}
                      </p>
                    )}
                  </div>
                </section>
              )}

              {/* Neural Cross-Encoder Reranker Attribution */}
              {re && re.enabled && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Cpu size={16} />
                    <span>Neural Cross-Encoder Attribution</span>
                  </h3>
                  <div className="evidence-card">
                    <div className="adjustments-row" style={{ borderTop: "none", paddingTop: 0 }}>
                      <span>Status: <strong>{re.fallback ? "Fallback (Baseline Preserved)" : "Applied"}</strong></span>
                      {typeof re.pre_rerank_score === "number" && typeof re.post_rerank_score === "number" && (
                        <span>Score: {re.pre_rerank_score.toFixed(4)} &rarr; {re.post_rerank_score.toFixed(4)}</span>
                      )}
                      <span>Adjustment: <strong>{re.adjustment > 0 ? "+" : ""}{re.adjustment.toFixed(4)}</strong></span>
                    </div>
                    {re.description && (
                      <p className="topic-evidence-desc">{re.description}</p>
                    )}
                  </div>
                </section>
              )}

              {/* Diversity & Novelty Mechanics (Phase 2.5E) */}
              {de && de.enabled && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Shuffle size={16} />
                    <span>Diversity & Novelty Mechanics</span>
                  </h3>
                  <div className="evidence-card">
                    <div className="adjustments-row" style={{ borderTop: "none", paddingTop: 0 }}>
                      <span>Adjustment: <strong>{de.adjustment > 0 ? "+" : ""}{de.adjustment.toFixed(4)}</strong></span>
                      {de.novelty_score !== null && de.novelty_score !== undefined && (
                        <span>Novelty: {(de.novelty_score * 100).toFixed(0)}%</span>
                      )}
                      {de.redundancy_score !== null && de.redundancy_score !== undefined && (
                        <span>Redundancy: {(de.redundancy_score * 100).toFixed(0)}%</span>
                      )}
                    </div>

                    {de.novelty_reasons && de.novelty_reasons.length > 0 && (
                      <div>
                        <span className="evidence-stat-label">Novelty Factors:</span>
                        <ul className="evidence-summary-list">
                          {de.novelty_reasons.map((reason, idx) => (
                            <li key={idx}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {de.redundancy_reasons && de.redundancy_reasons.length > 0 && (
                      <div>
                        <span className="evidence-stat-label">Redundancy Factors:</span>
                        <ul className="evidence-summary-list">
                          {de.redundancy_reasons.map((reason, idx) => (
                            <li key={idx}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {de.description && (
                      <p className="topic-evidence-desc">{de.description}</p>
                    )}
                  </div>
                </section>
              )}

              {/* Signal Contribution Breakdown */}
              {contributions.length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title">Signal Contribution Breakdown</h3>
                  <div className="signals-breakdown">
                    {contributions.map((sig) => {
                      const sharePct = ((sig.contribution / totalContribution) * 100).toFixed(0);
                      const label = SIGNAL_LABELS[sig.signal_name] || sig.signal_name.replace(/_/g, " ");
                      const isZeroWeight = sig.weight === 0.0 || sig.is_active === false;

                      return (
                        <div
                          key={sig.signal_name}
                          className={`signal-row ${isZeroWeight ? "inactive" : ""}`}
                        >
                          <div className="signal-meta">
                            <div className="signal-name-wrap">
                              <span className="signal-name">{label}</span>
                              {sig.is_primary_driver && (
                                <span className="primary-tag">Primary</span>
                              )}
                              {isZeroWeight && (
                                <span className="zero-weight-tag">Zero Weight</span>
                              )}
                            </div>
                            <div className="signal-stats">
                              <span className="signal-assessment">{sig.qualitative_assessment}</span>
                              <span className="signal-score">
                                Score: {(sig.score * 100).toFixed(0)}% | W: {(sig.weight * 100).toFixed(0)}% | C: +{sig.contribution.toFixed(4)}
                                {sig.raw_value !== null && sig.raw_value !== undefined && (
                                  <span> (Raw: {String(sig.raw_value)})</span>
                                )}
                              </span>
                            </div>
                          </div>

                          <div className="signal-bar-track">
                            <div
                              className={`signal-bar-fill ${sig.is_primary_driver ? "primary-bar" : ""}`}
                              style={{ width: `${Math.min(100, Math.max(0, sig.score * 100))}%` }}
                            />
                          </div>
                          {!isZeroWeight && (
                            <span className="signal-share-text">{sharePct}% of base score</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Topic Overlap Evidence */}
              {explanation.topic_evidence && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Tag size={16} />
                    <span>Topic Overlap & Proximity</span>
                  </h3>
                  {explanation.topic_evidence.shared_topic_names.length > 0 ? (
                    <div className="topics-evidence-box">
                      <div className="shared-topics-tags">
                        {explanation.topic_evidence.shared_topic_names.map((name) => (
                          <span key={name} className="topic-badge">
                            {name}
                          </span>
                        ))}
                      </div>
                      <p className="topic-evidence-desc">
                        {explanation.topic_evidence.description || "Exact canonical topic match identified."}
                      </p>
                    </div>
                  ) : (
                    <p className="topic-evidence-empty">
                      {explanation.topic_evidence.description || "No shared canonical topics identified."}
                    </p>
                  )}
                </section>
              )}

              {/* Provenance Evidence */}
              {explanation.provenance_evidence && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Database size={16} />
                    <span>Retrieval Channel Provenance</span>
                  </h3>
                  <div className="provenance-box">
                    <div className="provenance-sources">
                      {explanation.provenance_evidence.retrieval_sources.map((src) => (
                        <span key={src} className="provenance-badge">
                          {src === "semantic" ? "Dense Semantic Embeddings" : src === "lexical" ? "PostgreSQL Cover Density FTS" : src}
                        </span>
                      ))}
                    </div>
                    <p className="provenance-desc">{explanation.provenance_evidence.description}</p>
                  </div>
                </section>
              )}

              {/* Strengths & Limitations */}
              <div className="strengths-limitations-grid">
                {explanation.strengths.length > 0 && (
                  <div className="strengths-column">
                    <h4 className="strengths-heading">
                      <CheckCircle2 size={16} />
                      <span>Strengths</span>
                    </h4>
                    <ul className="strengths-list">
                      {explanation.strengths.map((str, idx) => (
                        <li key={idx}>{str}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {explanation.limitations.length > 0 && (
                  <div className="limitations-column">
                    <h4 className="limitations-heading">
                      <AlertCircle size={16} />
                      <span>Limitations</span>
                    </h4>
                    <ul className="limitations-list">
                      {explanation.limitations.map((lim, idx) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </>
          )}

          {/* TAB 2: TRUST & PUBLICATION INTEGRITY (Phase 2.6F) */}
          {(activeTab === "risk" || !explanation) && riskExplanation && (
            <div className="trust-risk-tab-content">
              {/* Trust Metric Header Card */}
              <div className={`drawer-metric-card risk-metric-card ${riskExplanation.risk_level.toLowerCase()}`}>
                <div className="metric-item">
                  <span className="metric-label">Risk Level</span>
                  <span className={`metric-value risk-level-tag ${riskExplanation.risk_level.toLowerCase()}`}>
                    {riskExplanation.risk_level.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Calibrated Risk Score</span>
                  <span className="metric-value">
                    {(riskExplanation.risk_score * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Assessment Confidence</span>
                  <span className="metric-value">
                    {(riskExplanation.risk_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Evidence Sufficiency</span>
                  <span className={`sufficiency-badge ${riskExplanation.evidence_sufficiency.toLowerCase()}`}>
                    {riskExplanation.evidence_sufficiency}
                  </span>
                </div>
              </div>

              {/* Natural Language Synthesis */}
              <section className="drawer-section">
                <h3 className="section-title">
                  <HelpCircle size={16} />
                  <span>Trust & Safety Assessment Synthesis</span>
                </h3>
                <p className="explanation-summary risk-summary-text">{riskExplanation.summary}</p>
              </section>

              {/* Mathematical Formulation & Trust Mitigation Attribution */}
              <section className="drawer-section">
                <h3 className="section-title">
                  <Scale size={16} />
                  <span>Deterministic Score Attribution (Phase 2.6C)</span>
                </h3>
                <div className="score-breakdown-card">
                  <div className="subtotals-grid">
                    <div className="subtotal-item">
                      <span className="subtotal-label">Gross Suspicious Score</span>
                      <span className="subtotal-val negative-color">
                        +{riskExplanation.gross_negative_score.toFixed(4)}
                      </span>
                    </div>
                    <div className="subtotal-item">
                      <span className="subtotal-label">Trust Mitigation Deducted</span>
                      <span className="subtotal-val positive-color">
                        -{riskExplanation.trust_mitigation_score.toFixed(4)}
                      </span>
                    </div>
                    <div className="subtotal-item">
                      <span className="subtotal-label">Final Bounded Risk Score</span>
                      <span className="subtotal-val">
                        ={riskExplanation.risk_score.toFixed(4)}
                      </span>
                    </div>
                  </div>

                  {riskExplanation.risk_reasons.length > 0 && (
                    <div className="risk-reasons-container">
                      <span className="evidence-stat-label">Assessment Justifications:</span>
                      <ul className="evidence-summary-list">
                        {riskExplanation.risk_reasons.map((r, idx) => (
                          <li key={idx}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </section>

              {/* Positive Trust Evidence */}
              {riskExplanation.positive_trust_signals.length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title positive-header">
                    <ShieldCheck size={16} />
                    <span>Verified Academic Trust Signals ({riskExplanation.positive_trust_signals.length})</span>
                  </h3>
                  <div className="evidence-signals-list">
                    {riskExplanation.positive_trust_signals.map((sig, idx) => (
                      <div key={idx} className="evidence-signal-card trust-card">
                        <div className="signal-card-header">
                          <span className="signal-title">{sig.explanation}</span>
                          <span className="provenance-pill">{sig.provenance}</span>
                        </div>
                        <div className="signal-card-meta">
                          <span>Field: <strong>{sig.source_field}</strong></span>
                          {sig.matched_value && <span>Matched: <em>"{sig.matched_value}"</em></span>}
                          <span>Strength: <strong>{sig.strength}</strong></span>
                          <span>Confidence: <strong>{sig.confidence}</strong></span>
                          <span className="contrib-val positive-color">Trust Value: +{sig.contribution.toFixed(4)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Suspicious Risk Evidence */}
              {riskExplanation.suspicious_signals.length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title suspicious-header">
                    <ShieldAlert size={16} />
                    <span>Suspicious & Cautionary Signals ({riskExplanation.suspicious_signals.length})</span>
                  </h3>
                  <div className="evidence-signals-list">
                    {riskExplanation.suspicious_signals.map((sig, idx) => (
                      <div key={idx} className={`evidence-signal-card ${sig.severity.toLowerCase()}-card`}>
                        <div className="signal-card-header">
                          <span className="signal-title">{sig.explanation}</span>
                          <span className="provenance-pill">{sig.provenance}</span>
                        </div>
                        <div className="signal-card-meta">
                          <span>Field: <strong>{sig.source_field}</strong></span>
                          {sig.matched_value && <span>Matched: <em>"{sig.matched_value}"</em></span>}
                          <span>Strength: <strong>{sig.strength}</strong></span>
                          <span>Severity: <strong className={`severity-text ${sig.severity.toLowerCase()}`}>{sig.severity}</strong></span>
                          <span className="contrib-val negative-color">Gross Contrib: +{sig.contribution.toFixed(4)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Neutral & Missing Metadata Evidence */}
              {riskExplanation.neutral_signals.length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title neutral-header">
                    <Info size={16} />
                    <span>Metadata Availability & Neutral Observations</span>
                  </h3>
                  <div className="evidence-signals-list">
                    {riskExplanation.neutral_signals.map((sig, idx) => (
                      <div key={idx} className="evidence-signal-card neutral-card">
                        <div className="signal-card-header">
                          <span className="signal-title">{sig.explanation}</span>
                          <span className="provenance-pill">{sig.provenance}</span>
                        </div>
                        <div className="signal-card-meta">
                          <span>Field: <strong>{sig.source_field}</strong></span>
                          <span className="neutral-note">Neutral observation (Missing data ≠ Predatory)</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Cross-Source Resolved Entity (Phase 2.6D) */}
              {riskExplanation.resolved_entity && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Database size={16} />
                    <span>Cross-Source Resolved Venue Entity</span>
                  </h3>
                  <div className="evidence-card">
                    <div className="evidence-grid">
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Canonical Venue Name</span>
                        <span className="evidence-stat-value">
                          {String(riskExplanation.resolved_entity.canonical_name || "Unresolved")}
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Entity Classification</span>
                        <span className="evidence-stat-value">
                          {String(riskExplanation.resolved_entity.entity_type || "UNKNOWN")}
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">Publisher / Society</span>
                        <span className="evidence-stat-value">
                          {String(riskExplanation.resolved_entity.publisher || riskExplanation.resolved_entity.organizer || "Unspecified")}
                        </span>
                      </div>
                      <div className="evidence-stat">
                        <span className="evidence-stat-label">ISSN / ISSN-L</span>
                        <span className="evidence-stat-value">
                          {String(riskExplanation.resolved_entity.issn_l || riskExplanation.resolved_entity.issn || "None")}
                        </span>
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {/* Provenance Distribution Summary */}
              {Object.keys(riskExplanation.provenance_summary).length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <Database size={16} />
                    <span>Intelligence Provenance Breakdown</span>
                  </h3>
                  <div className="provenance-box">
                    <div className="provenance-sources">
                      {Object.entries(riskExplanation.provenance_summary).map(([prov, count]) => (
                        <span key={prov} className="provenance-badge">
                          {prov}: {count} signal{count > 1 ? "s" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                </section>
              )}

              {/* Safety Disclaimers & Neutrality Limitations */}
              {riskExplanation.limitations.length > 0 && (
                <section className="drawer-section">
                  <h3 className="section-title">
                    <AlertCircle size={16} />
                    <span>Advisory Disclaimers & Limitations</span>
                  </h3>
                  <div className="limitations-column" style={{ width: "100%" }}>
                    <ul className="limitations-list">
                      {riskExplanation.limitations.map((lim, idx) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
