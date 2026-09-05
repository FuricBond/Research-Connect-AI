"use client";

import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  Calendar,
  Compass,
  ExternalLink,
  HelpCircle,
  Quote,
  Sparkles,
  Unlock,
} from "lucide-react";
import type { SimilarResearchItem } from "../../types/discovery";
import { setSelectedWork } from "../../hooks/useSelectedWork";

interface SimilarResearchCardProps {
  item: SimilarResearchItem;
  onExplain: (item: SimilarResearchItem) => void;
}

export function SimilarResearchCard({ item, onExplain }: SimilarResearchCardProps) {
  const { work, rank, combined_similarity, semantic_similarity, lexical_similarity, topic_similarity, explanation } = item;
  const router = useRouter();

  const simPct = (combined_similarity * 100).toFixed(0);

  const handleMatchOpportunities = () => {
    setSelectedWork(work);
    router.push("/opportunities");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <article className="research-card similar-card" aria-labelledby={`similar-title-${work.id}`}>
      {/* Card Header: Rank & Similarity */}
      <div className="card-top-row">
        <div className="rank-badge">
          <span>#{rank}</span>
        </div>

        <div className="score-group">
          <div className="score-meter" title={`Combined Similarity Score: ${simPct}%`}>
            <span className="score-label">Similarity</span>
            <strong className="score-number">{simPct}%</strong>
          </div>

          {explanation && (
            <button
              type="button"
              className="explain-btn"
              onClick={() => onExplain(item)}
              title="View detailed signal breakdown"
            >
              <HelpCircle size={14} />
              <span>Why similar?</span>
            </button>
          )}
        </div>
      </div>

      {/* Paper Title */}
      <h3 id={`similar-title-${work.id}`} className="paper-title">
        {work.landing_page_url ? (
          <a href={work.landing_page_url} target="_blank" rel="noopener noreferrer">
            {work.title}
            <ExternalLink size={14} className="inline-link-icon" />
          </a>
        ) : (
          work.title
        )}
      </h3>

      {/* Bibliographic Metadata */}
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
        {work.doi && (
          <a
            href={`https://doi.org/${work.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="meta-item doi-link"
          >
            <span>DOI:{work.doi}</span>
          </a>
        )}
      </div>

      {/* Shared Topics */}
      {item.shared_topic_names && item.shared_topic_names.length > 0 && (
        <div className="shared-topics-row">
          <Compass size={13} className="topics-icon" />
          <span className="topics-label">Shared topics:</span>
          <span className="topics-list">{item.shared_topic_names.slice(0, 4).join(" - ")}</span>
        </div>
      )}

      {/* Sub-scores */}
      <div className="signal-subscores-bar">
        {semantic_similarity > 0 && (
          <span className="subscore-item">
            Semantic: <strong>{(semantic_similarity * 100).toFixed(0)}%</strong>
          </span>
        )}
        {lexical_similarity > 0 && (
          <span className="subscore-item">
            Lexical: <strong>{(lexical_similarity * 100).toFixed(0)}%</strong>
          </span>
        )}
        {topic_similarity > 0 && (
          <span className="subscore-item">
            Topic: <strong>{(topic_similarity * 100).toFixed(0)}%</strong>
          </span>
        )}
      </div>

      {/* Footer Actions */}
      <footer className="card-actions-footer">
        <button
          type="button"
          className="action-btn primary-btn"
          onClick={handleMatchOpportunities}
        >
          <Sparkles size={15} />
          <span>Match Calls for This Paper</span>
          <ArrowRight size={14} />
        </button>
      </footer>
    </article>
  );
}
