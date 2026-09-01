import React, { useState } from "react";
import {
  BookOpen,
  Calendar,
  Compass,
  ExternalLink,
  HelpCircle,
  Quote,
  Sparkles,
  Unlock,
} from "lucide-react";
import type { ResearchSearchResultItem, ResearchWorkRead } from "../../types/discovery";

interface ResearchResultCardProps {
  item: ResearchSearchResultItem;
  onFindSimilar: (work: ResearchWorkRead) => void;
  onMatchOpportunities: (work: ResearchWorkRead) => void;
  onExplain: (item: ResearchSearchResultItem) => void;
}

export const ResearchResultCard: React.FC<ResearchResultCardProps> = ({
  item,
  onFindSimilar,
  onMatchOpportunities,
  onExplain,
}) => {
  const [isAbstractExpanded, setIsAbstractExpanded] = useState(false);
  const { work, rank, final_score, semantic_score, lexical_score, topic_score, explanation } = item;

  const scorePct = (final_score * 100).toFixed(0);

  return (
    <article className="research-card" aria-labelledby={`work-title-${work.id}`}>
      {/* Card Header: Rank & Relevance Indicator */}
      <div className="card-top-row">
        <div className="rank-badge">
          <span>#{rank}</span>
        </div>

        <div className="score-group">
          <div className="score-meter" title={`Composite Relevance Score: ${scorePct}%`}>
            <span className="score-label">Match</span>
            <strong className="score-number">{scorePct}%</strong>
          </div>

          {explanation && (
            <button
              type="button"
              className="explain-btn"
              onClick={() => onExplain(item)}
              title="View detailed signal breakdown and ranking rationale"
            >
              <HelpCircle size={14} />
              <span>Why this rank?</span>
            </button>
          )}
        </div>
      </div>

      {/* Paper Title */}
      <h3 id={`work-title-${work.id}`} className="paper-title">
        {work.landing_page_url ? (
          <a href={work.landing_page_url} target="_blank" rel="noopener noreferrer">
            {work.title}
            <ExternalLink size={14} className="inline-link-icon" />
          </a>
        ) : (
          work.title
        )}
      </h3>

      {/* Bibliographic Metadata Row */}
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
          <span className="meta-item citation-pill" title={`${work.cited_by_count} academic citations`}>
            <Quote size={12} />
            <span>{work.cited_by_count} citations</span>
          </span>
        )}

        {work.is_oa && (
          <span className="meta-item oa-badge" title="Open Access publication">
            <Unlock size={12} />
            <span>Open Access</span>
          </span>
        )}

        {work.doi && (
          <a
            href={`https://doi.org/${work.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="meta-item doi-link"
            title={`DOI: ${work.doi}`}
          >
            <span>DOI:{work.doi}</span>
          </a>
        )}
      </div>

      {/* Abstract Excerpt */}
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
              {isAbstractExpanded ? "Show less" : "Read full abstract"}
            </button>
          )}
        </div>
      )}

      {/* Signal Sub-Scores Indicator */}
      <div className="signal-subscores-bar">
        {semantic_score !== null && semantic_score !== undefined && (
          <span className="subscore-item" title="Semantic dense vector similarity">
            Semantic: <strong>{(semantic_score * 100).toFixed(0)}%</strong>
          </span>
        )}
        {lexical_score !== null && lexical_score !== undefined && (
          <span className="subscore-item" title="PostgreSQL FTS lexical cover density score">
            Lexical: <strong>{(lexical_score * 100).toFixed(0)}%</strong>
          </span>
        )}
        {topic_score !== null && topic_score !== undefined && topic_score > 0 && (
          <span className="subscore-item" title="Canonical topic overlap score">
            Topic: <strong>{(topic_score * 100).toFixed(0)}%</strong>
          </span>
        )}
      </div>

      {/* Card Footer: Action Buttons */}
      <footer className="card-actions-footer">
        <button
          type="button"
          className="action-btn secondary-btn"
          onClick={() => onFindSimilar(work)}
        >
          <Compass size={15} />
          <span>Find Similar Research</span>
        </button>

        <button
          type="button"
          className="action-btn primary-btn"
          onClick={() => onMatchOpportunities(work)}
        >
          <Sparkles size={15} />
          <span>Match Calls & Venues</span>
        </button>
      </footer>
    </article>
  );
};
