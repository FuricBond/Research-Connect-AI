"use client";

import { useState } from "react";
import Link from "next/link";
import { Building2, ChevronDown, ChevronUp, FileText, Mail, Megaphone, UserCheck } from "lucide-react";
import type { PeerMatchTier } from "../../types/peer";
import { COLLABORATION_STATUS_LABELS, PEER_TIER_LABELS } from "../../types/peer";
import { POSTING_TYPE_LABELS } from "../../types/posting";
import type { MatchingPaper, SupervisorMatch } from "../../types/supervisor";
import { SUPERVISOR_SIGNAL_LABELS } from "../../types/supervisor";

const TIER_TONE: Record<PeerMatchTier, string> = {
  STRONG: "status-OPEN",
  MODERATE: "status-FILLED",
  EXPLORATORY: "status-DRAFT",
  INSUFFICIENT_EVIDENCE: "status-ARCHIVED",
};

function paperHref(paper: MatchingPaper): string | null {
  if (paper.doi) return `https://doi.org/${paper.doi}`;
  return paper.landing_page_url;
}

/**
 * One supervisor suggestion.
 *
 * The score, tier, matching papers and signal breakdown all come from the server. A faculty
 * member's institution or email arriving as null means they chose not to disclose it, so those
 * fields are omitted rather than shown as "unknown", which would misrepresent a deliberate choice
 * as missing data.
 */
export function SupervisorMatchCard({ match }: { match: SupervisorMatch }) {
  const [showSignals, setShowSignals] = useState(false);
  const { supervisor } = match;

  return (
    <article className="posting-card">
      <div className="posting-card-head">
        <h3 className="posting-card-title">{supervisor.full_name ?? "Unnamed researcher"}</h3>
        <div className="posting-badges">
          <span className={`posting-badge ${TIER_TONE[match.tier]}`}>
            {PEER_TIER_LABELS[match.tier]}
          </span>
          <span className="posting-badge type">{Math.round(match.match_score * 100)}% fit</span>
        </div>
      </div>

      <div className="posting-meta">
        {supervisor.institution && (
          <span className="posting-meta-item">
            <Building2 size={13} aria-hidden="true" />
            {supervisor.institution}
            {supervisor.department ? ` · ${supervisor.department}` : ""}
          </span>
        )}
        {supervisor.academic_status && (
          <span className="posting-meta-item">{supervisor.academic_status}</span>
        )}
        <span className="posting-meta-item">
          <UserCheck size={13} aria-hidden="true" />
          {COLLABORATION_STATUS_LABELS[supervisor.collaboration_status]}
        </span>
        {supervisor.contact_email && (
          <a className="posting-meta-item" href={`mailto:${supervisor.contact_email}`}>
            <Mail size={13} aria-hidden="true" />
            {supervisor.contact_email}
          </a>
        )}
      </div>

      {supervisor.collaboration_note && (
        <p className="posting-summary">{supervisor.collaboration_note}</p>
      )}

      {match.explanation_reasons.length > 0 && (
        <ul className="peer-reasons">
          {match.explanation_reasons.map((reason, index) => (
            <li key={`${index}-${reason.slice(0, 24)}`}>{reason}</li>
          ))}
        </ul>
      )}

      {match.shared_topics.length > 0 && (
        <div className="peer-topic-groups">
          <div>
            <span className="peer-topic-label">Shared topics</span>
            <div className="posting-skills">
              {match.shared_topics.slice(0, 6).map((topic) => (
                <span key={topic} className="posting-skill">
                  {topic.replace(/-/g, " ")}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {match.matching_papers.length > 0 && (
        <section aria-label="Matching recent papers">
          <span className="peer-topic-label">Matching recent papers</span>
          <ul className="peer-reasons">
            {match.matching_papers.map((paper) => {
              const href = paperHref(paper);
              return (
                <li key={paper.work_id}>
                  <FileText size={12} aria-hidden="true" />{" "}
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      {paper.title}
                    </a>
                  ) : (
                    paper.title
                  )}
                  {paper.publication_year ? ` (${paper.publication_year})` : ""}
                  {` · ${Math.round(paper.similarity * 100)}% similar`}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {match.open_postings.length > 0 && (
        <section aria-label="Open postings">
          <span className="peer-topic-label">Open postings</span>
          <ul className="peer-reasons">
            {match.open_postings.map((posting) => (
              <li key={posting.posting_id}>
                <Megaphone size={12} aria-hidden="true" />{" "}
                <Link href={`/postings/${posting.posting_id}`}>{posting.title}</Link>
                {` · ${POSTING_TYPE_LABELS[posting.posting_type]}`}
                {posting.application_deadline
                  ? ` · apply by ${new Date(posting.application_deadline).toLocaleDateString()}`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div>
        <button
          type="button"
          className="posting-btn"
          onClick={() => setShowSignals((open) => !open)}
          aria-expanded={showSignals}
        >
          {showSignals ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          How this was scored
        </button>
        {showSignals && (
          <div className="peer-signals">
            <p className="posting-owner-note">
              Every suggestion is computed from your recorded research topics, preferred topics
              and publications with fixed weights. Confidence ({Math.round(match.confidence * 100)}%)
              reflects how much evidence the score rests on.
            </p>
            <table className="peer-signal-table">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Score</th>
                  <th>Contribution</th>
                </tr>
              </thead>
              <tbody>
                {match.signals.map((signal) => (
                  <tr key={signal.signal_type}>
                    <td>
                      {SUPERVISOR_SIGNAL_LABELS[signal.signal_type]}
                      <div className="peer-signal-explanation">{signal.explanation}</div>
                    </td>
                    <td>{signal.raw_score.toFixed(2)}</td>
                    <td>
                      {signal.weighted_contribution >= 0 ? "+" : ""}
                      {signal.weighted_contribution.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </article>
  );
}
