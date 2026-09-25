"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import "../../../styles/postings.css";
import { AlertCircle, ArrowLeft, ExternalLink, Mail } from "lucide-react";
import type { PostingStatus, ResearchPosting } from "../../../types/posting";
import {
  POSTING_STATUS_LABELS,
  POSTING_TYPE_LABELS,
  WORK_MODE_LABELS,
} from "../../../types/posting";
import { fetchPosting, transitionPosting } from "../../../services/api";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function PostingDetailPage() {
  const params = useParams<{ id: string }>();
  const postingId = params?.id;

  const [posting, setPosting] = useState<ResearchPosting | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!postingId) return;
    setLoading(true);
    setError(null);
    try {
      setPosting(await fetchPosting(postingId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load this posting");
      setPosting(null);
    } finally {
      setLoading(false);
    }
  }, [postingId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleTransition = async (target: PostingStatus) => {
    if (!posting) return;
    setBusy(true);
    setError(null);
    try {
      setPosting(await transitionPosting(posting.id, target));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update posting status");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="postings-loading">Loading posting…</div>;
  }

  if (error || !posting) {
    return (
      <div className="posting-detail">
        <Link href="/postings" className="posting-back-link">
          <ArrowLeft size={14} aria-hidden="true" />
          Back to postings
        </Link>
        <div className="postings-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>
            {error ??
              "This posting is not available. It may have been withdrawn, or it may still be an unpublished draft."}
          </span>
        </div>
      </div>
    );
  }

  const location = posting.location || posting.country || null;

  return (
    <div className="posting-detail">
      <Link href="/postings" className="posting-back-link">
        <ArrowLeft size={14} aria-hidden="true" />
        Back to postings
      </Link>

      <header className="posting-detail-head">
        <div className="posting-badges">
          <span className="posting-badge type">{POSTING_TYPE_LABELS[posting.posting_type]}</span>
          <span className={`posting-badge status-${posting.status}`}>
            {POSTING_STATUS_LABELS[posting.status]}
          </span>
          {posting.is_accepting_applications ? (
            <span className="posting-badge status-OPEN">Accepting applications</span>
          ) : (
            <span className="posting-badge deadline-passed">Not accepting applications</span>
          )}
        </div>
        <h1>{posting.title}</h1>
        <p className="posting-detail-author">
          {posting.author.full_name ?? "Unnamed researcher"}
          {posting.author.institution ? ` · ${posting.author.institution}` : ""}
          {posting.department ? ` · ${posting.department}` : ""}
        </p>
        {posting.summary && <p className="posting-summary">{posting.summary}</p>}
      </header>

      {posting.is_owner && posting.allowed_transitions.length > 0 && (
        <section className="posting-detail-section">
          <h2>Manage this posting</h2>
          <p className="posting-owner-note">
            You are the author. Only the transitions your posting’s current state allows are
            offered.
          </p>
          <div className="posting-card-actions">
            {posting.allowed_transitions.map((target) => (
              <button
                key={target}
                type="button"
                className={`posting-btn${target === "OPEN" ? " primary" : ""}`}
                disabled={busy}
                onClick={() => handleTransition(target)}
              >
                {target === "OPEN" ? "Publish" : `Mark ${POSTING_STATUS_LABELS[target]}`}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="posting-detail-section">
        <h2>About this opportunity</h2>
        <p className="posting-detail-body">{posting.description}</p>
      </section>

      {(posting.required_skills.length > 0 || posting.preferred_qualifications) && (
        <section className="posting-detail-section">
          <h2>What is expected</h2>
          {posting.required_skills.length > 0 && (
            <div className="posting-skills" style={{ marginBottom: "0.6rem" }}>
              {posting.required_skills.map((skill) => (
                <span key={skill} className="posting-skill">
                  {skill}
                </span>
              ))}
            </div>
          )}
          {posting.preferred_qualifications && (
            <p className="posting-detail-body">{posting.preferred_qualifications}</p>
          )}
        </section>
      )}

      <section className="posting-detail-section">
        <h2>Details</h2>
        <dl className="posting-detail-facts">
          <div className="posting-fact">
            <dt>Positions</dt>
            <dd>{posting.positions_available}</dd>
          </div>
          <div className="posting-fact">
            <dt>Work mode</dt>
            <dd>{WORK_MODE_LABELS[posting.work_mode]}</dd>
          </div>
          {location && (
            <div className="posting-fact">
              <dt>Location</dt>
              <dd>{location}</dd>
            </div>
          )}
          <div className="posting-fact">
            <dt>Application deadline</dt>
            <dd>
              {posting.application_deadline ? formatDate(posting.application_deadline) : "Open-ended"}
              {posting.days_until_deadline !== null && posting.days_until_deadline >= 0
                ? ` · ${posting.days_until_deadline} day${posting.days_until_deadline === 1 ? "" : "s"} left`
                : ""}
            </dd>
          </div>
          {posting.expected_start_date && (
            <div className="posting-fact">
              <dt>Expected start</dt>
              <dd>{formatDate(posting.expected_start_date)}</dd>
            </div>
          )}
          {posting.expected_end_date && (
            <div className="posting-fact">
              <dt>Expected end</dt>
              <dd>{formatDate(posting.expected_end_date)}</dd>
            </div>
          )}
          {posting.published_at && (
            <div className="posting-fact">
              <dt>Published</dt>
              <dd>{formatDate(posting.published_at)}</dd>
            </div>
          )}
        </dl>
      </section>

      {posting.topics.length > 0 && (
        <section className="posting-detail-section">
          <h2>Research topics</h2>
          <div className="posting-skills">
            {posting.topics.map((topic) => (
              <span key={topic.topic_id} className="posting-skill">
                {topic.name ?? topic.slug}
                {topic.is_primary ? " (primary)" : ""}
              </span>
            ))}
          </div>
        </section>
      )}

      {(posting.contact_email || posting.external_url) && (
        <section className="posting-detail-section">
          <h2>How to get in touch</h2>
          <div className="posting-card-actions">
            {posting.contact_email && (
              <a className="posting-btn" href={`mailto:${posting.contact_email}`}>
                <Mail size={13} aria-hidden="true" />
                {posting.contact_email}
              </a>
            )}
            {posting.external_url && (
              <a
                className="posting-btn"
                href={posting.external_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={13} aria-hidden="true" />
                Official page
              </a>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
