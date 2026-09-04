import React from "react";
import {
  Calendar,
  Clock,
  DollarSign,
  ExternalLink,
  Globe,
  HelpCircle,
  MapPin,
  Sparkles,
} from "lucide-react";
import type { OpportunityMatchItem } from "../../types/discovery";
import { QualityBadge } from "./QualityBadge";
import { RiskWarning } from "./RiskWarning";

interface OpportunityCardProps {
  item: OpportunityMatchItem;
  onExplain: (item: OpportunityMatchItem) => void;
}

export const OpportunityCard: React.FC<OpportunityCardProps> = ({ item, onExplain }) => {
  const { opportunity, rank, match_score, type_compatibility, topic_similarity, urgency, explanation } = item;

  const matchPct = (match_score * 100).toFixed(0);

  // Format deadline and compute remaining days
  let deadlineText = "No deadline specified";
  let isUrgent = false;
  let isPast = false;

  if (opportunity.submission_deadline) {
    const deadlineDate = new Date(opportunity.submission_deadline);
    const now = new Date();
    const diffMs = deadlineDate.getTime() - now.getTime();
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
      deadlineText = `Deadline passed (${deadlineDate.toLocaleDateString()})`;
      isPast = true;
    } else if (diffDays === 0) {
      deadlineText = "Deadline today!";
      isUrgent = true;
    } else if (diffDays <= 14) {
      deadlineText = `${diffDays} days remaining (${deadlineDate.toLocaleDateString()})`;
      isUrgent = true;
    } else {
      deadlineText = `Due ${deadlineDate.toLocaleDateString()} (${diffDays} days)`;
    }
  }

  // APC Extraction
  const apcData = opportunity.apc_or_fee as Record<string, unknown> | null;
  const isFree = apcData?.has_fee === false || apcData?.amount === 0;
  const hasApcAmount = typeof apcData?.amount === "number";

  return (
    <article
      className={`opportunity-card match-card ${opportunity.is_predatory_flag ? "card-predatory-flagged" : ""}`}
      aria-labelledby={`opp-title-${opportunity.id}`}
    >
      {/* Top Header: Rank, Type, Badges & Match Score */}
      <div className="card-top-row">
        <div className="card-top-left">
          <div className="rank-badge">
            <span>#{rank}</span>
          </div>
          <span className="tag opportunity-type-tag">
            {opportunity.opportunity_type.replace(/_/g, " ")}
          </span>
          <QualityBadge
            indexing={opportunity.indexing}
            status={opportunity.status}
            qualityScore={item.quality_score}
            showScore={true}
          />
        </div>

        <div className="score-group">
          <div className="score-meter opportunity-meter" title={`Composite Match Score: ${matchPct}%`}>
            <span className="score-label">Match</span>
            <strong className="score-number">{matchPct}%</strong>
          </div>

          {explanation && (
            <button
              type="button"
              className="explain-btn"
              onClick={() => onExplain(item)}
              title="Explain opportunity matching breakdown"
            >
              <HelpCircle size={14} />
              <span>Why matched?</span>
            </button>
          )}
        </div>
      </div>

      {/* Risk & Trust Warning Banner (Phase 2.6F) */}
      <RiskWarning
        isPredatory={opportunity.is_predatory_flag}
        riskScore={opportunity.risk_score}
        riskReasons={opportunity.risk_reasons}
        riskLevel={opportunity.risk_level}
        riskConfidence={opportunity.risk_confidence}
        onViewRiskDetails={() => onExplain(item)}
      />

      {/* Title */}
      <h3 id={`opp-title-${opportunity.id}`} className="opportunity-title">
        {opportunity.website_url ? (
          <a href={opportunity.website_url} target="_blank" rel="noopener noreferrer">
            {opportunity.title}
            <ExternalLink size={14} className="inline-link-icon" />
          </a>
        ) : (
          opportunity.title
        )}
      </h3>

      {/* Publisher / Organizer & Location & APC */}
      <div className="venue-meta-row">
        {(opportunity.publisher || opportunity.organizer) && (
          <p className="opportunity-publisher">
            Organized by: {opportunity.publisher || opportunity.organizer}
            {opportunity.series_name && ` • Series: ${opportunity.series_name}`}
          </p>
        )}

        <div className="venue-logistics">
          {opportunity.delivery_mode && (
            <span className="meta-item">
              <Globe size={13} />
              <span>{opportunity.delivery_mode}</span>
            </span>
          )}

          {opportunity.location && (
            <span className="meta-item">
              <MapPin size={13} />
              <span>{opportunity.location}</span>
            </span>
          )}

          {/* APC / Fee Indicator */}
          {apcData ? (
            <span className={`meta-item fee-badge ${isFree ? "fee-free" : "fee-paid"}`}>
              <DollarSign size={13} />
              <span>
                {isFree
                  ? "No Fee (Free OA)"
                  : hasApcAmount
                  ? `$${apcData.amount} ${(apcData.currency as string) || "USD"}`
                  : "Fee Applicable"}
              </span>
            </span>
          ) : (
            <span className="meta-item fee-badge fee-neutral">
              <DollarSign size={13} />
              <span>Fee Unspecified</span>
            </span>
          )}
        </div>
      </div>

      {/* Summary / Description snippet */}
      {(opportunity.summary || opportunity.description) && (
        <p className="opportunity-summary-text">
          {opportunity.summary || opportunity.description}
        </p>
      )}

      {/* Milestone Dates (Notification, Camera-ready) */}
      {(opportunity.notification_date || opportunity.camera_ready_deadline) && (
        <div className="milestones-row">
          {opportunity.notification_date && (
            <span className="milestone-item">
              <strong>Notice:</strong> {new Date(opportunity.notification_date).toLocaleDateString()}
            </span>
          )}
          {opportunity.camera_ready_deadline && (
            <span className="milestone-item">
              <strong>Camera-Ready:</strong> {new Date(opportunity.camera_ready_deadline).toLocaleDateString()}
            </span>
          )}
        </div>
      )}

      {/* Match Sub-Signals & Deadlines */}
      <div className="signal-subscores-bar">
        <span className="subscore-item">
          Type Fit: <strong>{(type_compatibility * 100).toFixed(0)}%</strong>
        </span>
        <span className="subscore-item">
          Topic Overlap: <strong>{(topic_similarity * 100).toFixed(0)}%</strong>
        </span>
        {urgency !== null && urgency !== undefined && urgency > 0 && (
          <span className="subscore-item">
            Urgency Fit: <strong>{(urgency * 100).toFixed(0)}%</strong>
          </span>
        )}
      </div>

      {/* Card Footer */}
      <footer className="opportunity-card-footer">
        <div className={`deadline-chip ${isUrgent ? "urgent-deadline" : isPast ? "past-deadline" : ""}`}>
          <Clock size={14} />
          <span>{deadlineText}</span>
        </div>

        {opportunity.submission_url && (
          <a
            href={opportunity.submission_url}
            target="_blank"
            rel="noopener noreferrer"
            className="action-btn primary-btn submission-link"
          >
            <span>Submit Manuscript</span>
            <ExternalLink size={14} />
          </a>
        )}
      </footer>
    </article>
  );
};
