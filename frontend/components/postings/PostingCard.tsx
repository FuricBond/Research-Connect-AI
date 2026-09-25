"use client";

import Link from "next/link";
import {
  Building2,
  CalendarClock,
  MapPin,
  Trash2,
  Users,
} from "lucide-react";
import type { PostingStatus, ResearchPosting } from "../../types/posting";
import {
  POSTING_STATUS_LABELS,
  POSTING_TYPE_LABELS,
  WORK_MODE_LABELS,
} from "../../types/posting";

/**
 * Renders the deadline as a badge.
 *
 * `days_until_deadline` is computed server-side; this only chooses how to phrase it, so the
 * urgency a researcher sees always matches the urgency the API reported.
 */
function DeadlineBadge({ posting }: { posting: ResearchPosting }) {
  if (posting.application_deadline === null) {
    return <span className="posting-badge">No deadline</span>;
  }
  const days = posting.days_until_deadline;
  if (days === null) return null;

  if (days < 0) {
    return <span className="posting-badge deadline-passed">Deadline passed</span>;
  }
  if (days === 0) {
    return <span className="posting-badge deadline-soon">Closes today</span>;
  }
  return (
    <span className={`posting-badge${days <= 7 ? " deadline-soon" : ""}`}>
      {days} day{days === 1 ? "" : "s"} left
    </span>
  );
}

export interface PostingCardProps {
  posting: ResearchPosting;
  /** Shown only to the author: lifecycle controls driven by `allowed_transitions`. */
  showOwnerControls?: boolean;
  onTransition?: (posting: ResearchPosting, target: PostingStatus) => void;
  onDelete?: (posting: ResearchPosting) => void;
  busy?: boolean;
}

export function PostingCard({
  posting,
  showOwnerControls = false,
  onTransition,
  onDelete,
  busy = false,
}: PostingCardProps) {
  const location = posting.location || posting.country || null;

  return (
    <article className="posting-card">
      <div className="posting-card-head">
        <h3 className="posting-card-title">
          <Link href={`/postings/${posting.id}`}>{posting.title}</Link>
        </h3>
        <div className="posting-badges">
          <span className="posting-badge type">{POSTING_TYPE_LABELS[posting.posting_type]}</span>
          <span className={`posting-badge status-${posting.status}`}>
            {POSTING_STATUS_LABELS[posting.status]}
          </span>
          <DeadlineBadge posting={posting} />
        </div>
      </div>

      <div className="posting-meta">
        {posting.author.full_name && (
          <span className="posting-meta-item">{posting.author.full_name}</span>
        )}
        {posting.institution && (
          <span className="posting-meta-item">
            <Building2 size={13} aria-hidden="true" />
            {posting.institution}
          </span>
        )}
        {location && (
          <span className="posting-meta-item">
            <MapPin size={13} aria-hidden="true" />
            {location} · {WORK_MODE_LABELS[posting.work_mode]}
          </span>
        )}
        <span className="posting-meta-item">
          <Users size={13} aria-hidden="true" />
          {posting.positions_available} position{posting.positions_available === 1 ? "" : "s"}
        </span>
        {posting.application_deadline && (
          <span className="posting-meta-item">
            <CalendarClock size={13} aria-hidden="true" />
            {new Date(posting.application_deadline).toLocaleDateString()}
          </span>
        )}
      </div>

      {posting.summary && <p className="posting-summary">{posting.summary}</p>}

      {posting.required_skills.length > 0 && (
        <div className="posting-skills">
          {posting.required_skills.slice(0, 8).map((skill) => (
            <span key={skill} className="posting-skill">
              {skill}
            </span>
          ))}
        </div>
      )}

      {showOwnerControls && posting.is_owner && (
        <div className="posting-card-actions">
          {posting.allowed_transitions.map((target) => (
            <button
              key={target}
              type="button"
              className={`posting-btn${target === "OPEN" ? " primary" : ""}`}
              disabled={busy}
              onClick={() => onTransition?.(posting, target)}
            >
              {target === "OPEN" ? "Publish" : `Mark ${POSTING_STATUS_LABELS[target]}`}
            </button>
          ))}
          {posting.status === "DRAFT" && onDelete && (
            <button
              type="button"
              className="posting-btn danger"
              disabled={busy}
              onClick={() => onDelete(posting)}
            >
              <Trash2 size={13} aria-hidden="true" />
              Delete draft
            </button>
          )}
        </div>
      )}
    </article>
  );
}
