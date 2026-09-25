"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import "../../../styles/postings.css";
import { AlertCircle, ArrowLeft, ExternalLink, Mail, Send } from "lucide-react";
import type {
  ApplicationStatus,
  PostingApplication,
  PostingStatus,
  ResearchPosting,
} from "../../../types/posting";
import {
  POSTING_STATUS_LABELS,
  POSTING_TYPE_LABELS,
  WORK_MODE_LABELS,
} from "../../../types/posting";
import { ApplicationCard } from "../../../components/postings/ApplicationCard";
import { OpeningTermsPanel } from "../../../components/postings/OpeningTermsPanel";
import {
  applyToPosting,
  fetchPosting,
  fetchPostingApplications,
  transitionApplication,
  transitionPosting,
} from "../../../services/api";

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

  // Phase 5.11 — applying, and reviewing as the author
  const [showApplyForm, setShowApplyForm] = useState(false);
  const [coverNote, setCoverNote] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applySubmitted, setApplySubmitted] = useState(false);
  const [applications, setApplications] = useState<PostingApplication[]>([]);
  const [applicationsError, setApplicationsError] = useState<string | null>(null);
  const [busyApplicationId, setBusyApplicationId] = useState<string | null>(null);

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

  // Only the author may enumerate a posting's applications, so this is loaded separately and
  // its failure never blocks the posting itself from rendering.
  const loadApplications = useCallback(async () => {
    if (!postingId) return;
    try {
      const listed = await fetchPostingApplications(postingId, { limit: 100 });
      setApplications(listed.applications);
      setApplicationsError(null);
    } catch (err) {
      setApplications([]);
      setApplicationsError(
        err instanceof Error ? err.message : "Failed to load applications for this posting"
      );
    }
  }, [postingId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (posting?.is_owner && posting.opening_terms.accepts_applications) {
      loadApplications();
    }
  }, [posting?.is_owner, posting?.opening_terms.accepts_applications, loadApplications]);

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

  const handleApply = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!posting) return;
    setBusy(true);
    setApplyError(null);
    try {
      await applyToPosting(posting.id, {
        cover_note: coverNote.trim() || null,
        contact_email: contactEmail.trim() || null,
        portfolio_url: portfolioUrl.trim() || null,
      });
      setApplySubmitted(true);
      setShowApplyForm(false);
      setCoverNote("");
      setContactEmail("");
      setPortfolioUrl("");
      await load();
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : "Failed to submit your application");
    } finally {
      setBusy(false);
    }
  };

  const handleApplicationTransition = async (
    application: PostingApplication,
    target: ApplicationStatus
  ) => {
    setBusyApplicationId(application.id);
    setApplicationsError(null);
    try {
      await transitionApplication(application.id, target);
      await loadApplications();
    } catch (err) {
      setApplicationsError(
        err instanceof Error ? err.message : "Failed to update the application"
      );
    } finally {
      setBusyApplicationId(null);
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

      <OpeningTermsPanel terms={posting.opening_terms} />

      {posting.opening_terms.accepts_applications && !posting.is_owner && (
        <section className="posting-detail-section">
          <h2>Apply for this opening</h2>
          {posting.viewer_application_status ? (
            <p className="posting-owner-note">
              You have already applied to this opening. Its current status is{" "}
              <strong>{posting.viewer_application_status}</strong>. Track it from{" "}
              <Link href="/postings/applications">My Applications</Link>.
            </p>
          ) : applySubmitted ? (
            <p className="posting-owner-note">
              Your application has been submitted. Track it from{" "}
              <Link href="/postings/applications">My Applications</Link>.
            </p>
          ) : !posting.is_accepting_applications ? (
            <p className="posting-owner-note">
              This opening is no longer accepting applications.
            </p>
          ) : showApplyForm ? (
            <form className="posting-form" onSubmit={handleApply}>
              <div className="posting-field">
                <label htmlFor="cover-note">
                  Statement of interest{" "}
                  <span className="posting-field-hint">what draws you to this work</span>
                </label>
                <textarea
                  id="cover-note"
                  value={coverNote}
                  onChange={(e) => setCoverNote(e.target.value)}
                  maxLength={5000}
                />
              </div>
              <div className="posting-form-grid">
                <div className="posting-field">
                  <label htmlFor="apply-email">Contact email</label>
                  <input
                    id="apply-email"
                    type="email"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                  />
                </div>
                <div className="posting-field">
                  <label htmlFor="apply-portfolio">
                    CV or portfolio link <span className="posting-field-hint">optional</span>
                  </label>
                  <input
                    id="apply-portfolio"
                    type="url"
                    value={portfolioUrl}
                    onChange={(e) => setPortfolioUrl(e.target.value)}
                  />
                </div>
              </div>
              {applyError && (
                <div className="postings-error" role="alert">
                  <AlertCircle size={15} aria-hidden="true" />
                  <span>{applyError}</span>
                </div>
              )}
              <div className="posting-form-actions">
                <button type="submit" className="posting-btn primary" disabled={busy}>
                  <Send size={13} aria-hidden="true" />
                  Submit application
                </button>
                <button
                  type="button"
                  className="posting-btn"
                  onClick={() => setShowApplyForm(false)}
                  disabled={busy}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              className="posting-btn primary"
              onClick={() => setShowApplyForm(true)}
            >
              <Send size={13} aria-hidden="true" />
              Apply now
            </button>
          )}
        </section>
      )}

      {posting.is_owner && posting.opening_terms.accepts_applications && (
        <section className="posting-detail-section">
          <h2>Applications ({posting.application_count})</h2>
          {applicationsError && (
            <div className="postings-error" role="alert">
              <AlertCircle size={15} aria-hidden="true" />
              <span>{applicationsError}</span>
            </div>
          )}
          {applications.length === 0 ? (
            <p className="posting-owner-note">No applications have been submitted yet.</p>
          ) : (
            <div className="postings-list">
              {applications.map((application) => (
                <ApplicationCard
                  key={application.id}
                  application={application}
                  onTransition={handleApplicationTransition}
                  busy={busyApplicationId === application.id}
                />
              ))}
            </div>
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
