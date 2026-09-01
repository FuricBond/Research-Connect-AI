import React, { useEffect } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  HelpCircle,
  Sparkles,
  Tag,
  X,
} from "lucide-react";
import type { ExplanationSchema } from "../../types/discovery";

interface ExplainabilityDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  explanation: ExplanationSchema | null;
  entityTitle: string;
  entityType?: "research_work" | "opportunity";
}

const SIGNAL_LABELS: Record<string, string> = {
  semantic_similarity: "Semantic Relevance",
  topic_similarity: "Canonical Topic Overlap",
  lexical_similarity: "Keyword / Lexical Match",
  type_compatibility: "Publication Type Compatibility",
  opportunity_quality: "Venue Indexing & Quality",
  urgency: "Deadline Proximity / Urgency",
  freshness: "Publication Recency",
};

export const ExplainabilityDrawer: React.FC<ExplainabilityDrawerProps> = ({
  isOpen,
  onClose,
  explanation,
  entityTitle,
  entityType = "research_work",
}) => {
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

  if (!isOpen || !explanation) return null;

  const contributions = Object.values(explanation.signal_contributions || {});
  const totalContribution = contributions.reduce((sum, c) => sum + c.contribution, 0) || 1.0;

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
              <span>Ranking Explainability & Evidence</span>
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

        <div className="drawer-body">
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
              <span className="metric-label">Evaluation Engine</span>
              <span className="metric-value-sm">Deterministic Hybrid Ranker</span>
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

          {/* Signal Contribution Breakdown */}
          {contributions.length > 0 && (
            <section className="drawer-section">
              <h3 className="section-title">Signal Contribution Breakdown</h3>
              <div className="signals-breakdown">
                {contributions.map((sig) => {
                  const sharePct = ((sig.contribution / totalContribution) * 100).toFixed(0);
                  const label = SIGNAL_LABELS[sig.signal_name] || sig.signal_name.replace(/_/g, " ");

                  return (
                    <div key={sig.signal_name} className="signal-row">
                      <div className="signal-meta">
                        <div className="signal-name-wrap">
                          <span className="signal-name">{label}</span>
                          {sig.is_primary_driver && (
                            <span className="primary-tag">Primary</span>
                          )}
                        </div>
                        <div className="signal-stats">
                          <span className="signal-assessment">{sig.qualitative_assessment}</span>
                          <span className="signal-score">
                            Raw: {(sig.score * 100).toFixed(0)}% (Weight: {(sig.weight * 100).toFixed(0)}%)
                          </span>
                        </div>
                      </div>

                      <div className="signal-bar-track">
                        <div
                          className={`signal-bar-fill ${sig.is_primary_driver ? "primary-bar" : ""}`}
                          style={{ width: `${Math.min(100, Math.max(0, sig.score * 100))}%` }}
                        />
                      </div>
                      <span className="signal-share-text">{sharePct}% of final score</span>
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
        </div>
      </div>
    </div>
  );
};
