"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, ChevronUp, EyeOff, Link2 } from "lucide-react";
import type { ApplicationStatus, PostingApplication } from "../../types/posting";
import { APPLICATION_STATUS_LABELS } from "../../types/posting";

/** Maps an application status onto the shared posting badge palette. */
const STATUS_TONE: Record<ApplicationStatus, string> = {
  SUBMITTED: "status-DRAFT",
  UNDER_REVIEW: "status-CLOSED",
  SHORTLISTED: "status-FILLED",
  OFFERED: "status-OPEN",
  ACCEPTED: "status-OPEN",
  DECLINED: "status-CANCELLED",
  REJECTED: "status-CANCELLED",
  WITHDRAWN: "status-ARCHIVED",
};

export interface ApplicationCardProps {
  application: PostingApplication;
  onTransition?: (application: PostingApplication, target: ApplicationStatus) => void;
  busy?: boolean;
}

/**
 * One application, rendered for whichever side is looking at it.
 *
 * `allowed_transitions` already reflects the viewer's role, so the buttons offered here are
 * exactly the moves the server will accept — an applicant is never shown "Shortlist".
 */
export function ApplicationCard({ application, onTransition, busy = false }: ApplicationCardProps) {
  const [showHistory, setShowHistory] = useState(false);
  const isAuthorView = application.is_posting_author;

  return (
    <article className="posting-card">
      <div className="posting-card-head">
        <h3 className="posting-card-title">
          {isAuthorView ? (
            application.applicant.full_name ?? "Unnamed applicant"
          ) : (
            <Link href={`/postings/${application.posting_id}`}>
              {application.posting_title ?? "Research posting"}
            </Link>
          )}
        </h3>
        <div className="posting-badges">
          <span className={`posting-badge ${STATUS_TONE[application.status]}`}>
            {APPLICATION_STATUS_LABELS[application.status]}
          </span>
        </div>
      </div>

      <div className="posting-meta">
        {isAuthorView && application.applicant.institution && (
          <span className="posting-meta-item">{application.applicant.institution}</span>
        )}
        {isAuthorView && application.applicant.academic_status && (
          <span className="posting-meta-item">{application.applicant.academic_status}</span>
        )}
        <span className="posting-meta-item">
          Submitted {new Date(application.submitted_at).toLocaleDateString()}
        </span>
        {application.contact_email && isAuthorView && (
          <a className="posting-meta-item" href={`mailto:${application.contact_email}`}>
            {application.contact_email}
          </a>
        )}
        {application.portfolio_url && isAuthorView && (
          <a
            className="posting-meta-item"
            href={application.portfolio_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Link2 size={12} aria-hidden="true" />
            Portfolio
          </a>
        )}
      </div>

      {application.cover_note && <p className="posting-summary">{application.cover_note}</p>}

      {application.decision_reason && (
        <p className="posting-owner-note">
          <strong>Decision note:</strong> {application.decision_reason}
        </p>
      )}

      {isAuthorView && application.reviewer_note && (
        <p className="posting-owner-note">
          <EyeOff size={12} aria-hidden="true" /> <strong>Private note (not shown to the
          applicant):</strong> {application.reviewer_note}
        </p>
      )}

      {application.allowed_transitions.length > 0 && (
        <div className="posting-card-actions">
          {application.allowed_transitions.map((target) => (
            <button
              key={target}
              type="button"
              className={`posting-btn${
                target === "OFFERED" || target === "ACCEPTED" ? " primary" : ""
              }${target === "REJECTED" || target === "WITHDRAWN" ? " danger" : ""}`}
              disabled={busy}
              onClick={() => onTransition?.(application, target)}
            >
              {APPLICATION_STATUS_LABELS[target]}
            </button>
          ))}
        </div>
      )}

      {application.status_history.length > 0 && (
        <div>
          <button
            type="button"
            className="posting-btn"
            onClick={() => setShowHistory((open) => !open)}
            aria-expanded={showHistory}
          >
            {showHistory ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            History ({application.status_history.length})
          </button>
          {showHistory && (
            <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.1rem", fontSize: "0.8125rem" }}>
              {application.status_history.map((event, index) => (
                <li key={`${event.to_status}-${event.at}-${index}`}>
                  {new Date(event.at).toLocaleString()} —{" "}
                  {event.from_status ? `${event.from_status} → ` : ""}
                  {event.to_status} (by {event.actor_role.toLowerCase()})
                  {event.reason ? `: ${event.reason}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
