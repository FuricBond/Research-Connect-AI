"use client";

import { useState } from "react";
import { Building2, ChevronDown, ChevronUp, Mail, UserCheck } from "lucide-react";
import type { PeerMatch, PeerMatchTier } from "../../types/peer";
import {
  COLLABORATION_INTEREST_LABELS,
  COLLABORATION_STATUS_LABELS,
  PEER_SIGNAL_LABELS,
  PEER_TIER_LABELS,
} from "../../types/peer";

const TIER_TONE: Record<PeerMatchTier, string> = {
  STRONG: "status-OPEN",
  MODERATE: "status-FILLED",
  EXPLORATORY: "status-DRAFT",
  INSUFFICIENT_EVIDENCE: "status-ARCHIVED",
};

/**
 * One peer suggestion.
 *
 * The score, its tier and the signal breakdown all come from the server. A peer's institution or
 * email arriving as null means they chose not to disclose it, so those fields are simply omitted
 * rather than shown as "unknown", which would misrepresent a deliberate choice as missing data.
 */
export function PeerMatchCard({ match }: { match: PeerMatch }) {
  const [showSignals, setShowSignals] = useState(false);
  const { peer } = match;

  return (
    <article className="posting-card">
      <div className="posting-card-head">
        <h3 className="posting-card-title">{peer.full_name ?? "Unnamed researcher"}</h3>
        <div className="posting-badges">
          <span className={`posting-badge ${TIER_TONE[match.tier]}`}>
            {PEER_TIER_LABELS[match.tier]}
          </span>
          <span className="posting-badge type">{Math.round(match.match_score * 100)}% match</span>
        </div>
      </div>

      <div className="posting-meta">
        {peer.institution && (
          <span className="posting-meta-item">
            <Building2 size={13} aria-hidden="true" />
            {peer.institution}
            {peer.department ? ` · ${peer.department}` : ""}
          </span>
        )}
        {peer.academic_status && <span className="posting-meta-item">{peer.academic_status}</span>}
        <span className="posting-meta-item">
          <UserCheck size={13} aria-hidden="true" />
          {COLLABORATION_STATUS_LABELS[peer.collaboration_status]}
        </span>
        {peer.contact_email && (
          <a className="posting-meta-item" href={`mailto:${peer.contact_email}`}>
            <Mail size={13} aria-hidden="true" />
            {peer.contact_email}
          </a>
        )}
      </div>

      {peer.collaboration_note && <p className="posting-summary">{peer.collaboration_note}</p>}

      {match.explanation_reasons.length > 0 && (
        <ul className="peer-reasons">
          {match.explanation_reasons.map((reason, index) => (
            <li key={`${index}-${reason.slice(0, 24)}`}>{reason}</li>
          ))}
        </ul>
      )}

      {(match.shared_topics.length > 0 || match.complementary_topics.length > 0) && (
        <div className="peer-topic-groups">
          {match.shared_topics.length > 0 && (
            <div>
              <span className="peer-topic-label">Shared</span>
              <div className="posting-skills">
                {match.shared_topics.slice(0, 6).map((topic) => (
                  <span key={topic} className="posting-skill">
                    {topic.replace(/-/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
          {match.complementary_topics.length > 0 && (
            <div>
              <span className="peer-topic-label">They add</span>
              <div className="posting-skills">
                {match.complementary_topics.slice(0, 6).map((topic) => (
                  <span key={topic} className="posting-skill complementary">
                    {topic.replace(/-/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {peer.collaboration_interests.length > 0 && (
        <div className="posting-skills">
          {peer.collaboration_interests.map((interest) => (
            <span key={interest} className="posting-skill">
              {COLLABORATION_INTEREST_LABELS[interest]}
            </span>
          ))}
        </div>
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
              Every suggestion is computed from recorded research topics with fixed weights, and
              confidence ({Math.round(match.confidence * 100)}%) reflects how much evidence the
              score rests on — a thin profile can match highly by coincidence.
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
                      {PEER_SIGNAL_LABELS[signal.signal_type]}
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
