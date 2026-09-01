import React, { useState } from "react";
import {
  BookOpen,
  Calendar,
  ExternalLink,
  HelpCircle,
  Quote,
  Sparkles,
  Tag,
  Unlock,
} from "lucide-react";
import type { ResearchWorkRead, SimilarResearchItem } from "../../types/discovery";

interface SimilarResearchCardProps {
  item: SimilarResearchItem;
  onMatchOpportunities: (work: ResearchWorkRead) => void;
  onExplain: (item: SimilarResearchItem) => void;
}

export const SimilarResearchCard: React.FC<SimilarResearchCardProps> = ({
  item,
  onMatchOpportunities,
  onExplain,
}) => {
  const [isAbstractExpanded, setIsAbstractExpanded] = useState(false);
  const {
    work,
    rank,
    combined_similarity,
    semantic_similarity,
    topic_similarity,
    freshness,
    shared_topic_names,
    explanation,
  } = item;

  const simPct = (combined_similarity * 100).toFixed(0);

  return (
    <article className="research-card similar-card" aria-labelledby={`sim-title-${work.id}`}>
      {/* Header */}
      <div className="card-top-row">
        <div className="rank-badge">
          <span>#{rank}</span>
        </div>

        <div className="score-group">
          <div className="score-meter similarity-meter" title={`Combined Similarity: ${simPct}%`}>
            <span className="score-label">Similarity</span>
            <strong className="score-number">{simPct}%</strong>
          </div>

          {explanation && (
            <button
              type="button"
              className="explain-btn"
              onClick={() => onExplain(item)}
              title="Explain similarity signals"
            >
              <HelpCircle size={14} />
              <span>Explain</span>
            </button>
          )}
        </div>
      </div>

      {/* Title */}
      <h3 id={`sim-title-${work.id}`} className="paper-title">
        {work.landing_page_url ? (
          <a href={work.landing_page_url} target="_blank" rel="noopener noreferrer">
            {work.title}
            <ExternalLink size={14} className="inline-link-icon" />
          </a>
        ) : (
          work.title
        )}
      </h3>

      {/* Metadata */}
      <div className="paper-metadata-row">
        {work.publication_year && (
          <span className="meta-item">
            <Calendar size={13} />
            <span>{work.publication_year}</span>
          </span>
        )}

        {work.work_type && (
          <span className="meta-item">
            <BookOpen size={13} />
            <span className="capitalize">{work.work_type.replace(/_/g, " ")}</span>
          </span>
        )}

        {work.cited_by_count !== null && work.cited_by_count !== undefined && (
          <span className="meta-item citation-pill">
            <Quote size={12} />
            <span>{work.cited_by_count} citations</span>
          </span>
        )}

        {work.is_oa && (
          <span className="meta-item oa-badge">
            <Unlock size={12} />
            <span>Open Access</span>
          </span>
        )}
      </div>

      {/* Shared Canonical Topics */}
      {shared_topic_names.length > 0 && (
        <div className="shared-topics-row">
          <Tag size={13} className="topic-icon" />
          <span className="shared-topic-label">Shared Topics:</span>
          <div className="topics-list">
            {shared_topic_names.map((t) => (
              <span key={t} className="shared-topic-pill">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Abstract */}
      {work.abstract && (
        <div className="abstract-container">
          <p className={`abstract-text ${isAbstractExpanded ? "expanded" : "clamped"}`}>
            {work.abstract}
          </p>
          {work.abstract.length > 220 && (
            <button
              type="button"
              className="abstract-toggle-btn"
              onClick={() => setIsAbstractExpanded(!isAbstractExpanded)}
            >
              {isAbstractExpanded ? "Show less" : "Read abstract"}
            </button>
          )}
        </div>
      )}

      {/* Signal Sub-scores */}
      <div className="signal-subscores-bar">
        <span className="subscore-item">
          Vector Sim: <strong>{(semantic_similarity * 100).toFixed(0)}%</strong>
        </span>
        {topic_similarity > 0 && (
          <span className="subscore-item">
            Topic Overlap: <strong>{(topic_similarity * 100).toFixed(0)}%</strong>
          </span>
        )}
        {freshness !== null && freshness !== undefined && freshness > 0 && (
          <span className="subscore-item">
            Recency: <strong>{(freshness * 100).toFixed(0)}%</strong>
          </span>
        )}
      </div>

      {/* Footer */}
      <footer className="card-actions-footer">
        <button
          type="button"
          className="action-btn primary-btn"
          onClick={() => onMatchOpportunities(work)}
        >
          <Sparkles size={15} />
          <span>Match Calls for This Paper</span>
        </button>
      </footer>
    </article>
  );
};
