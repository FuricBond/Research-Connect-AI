"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../styles/postings.css";
import { AlertCircle, Loader2, Plus, RefreshCw, Search, X } from "lucide-react";
import { PostingCard } from "../../components/postings/PostingCard";
import type {
  CommitmentType,
  CompensationType,
  OpeningTermsUpdate,
  PostingCreatePayload,
  PostingFilterParams,
  PostingStatus,
  PostingSummaryResponse,
  PostingType,
  PostingWorkMode,
  ResearchPosting,
} from "../../types/posting";
import {
  COMMITMENT_TYPE_LABELS,
  COMPENSATION_TYPE_LABELS,
  POSTING_TYPE_LABELS,
  STRUCTURED_OPENING_TYPES,
  WORK_MODE_LABELS,
} from "../../types/posting";
import {
  createPosting,
  deletePosting,
  fetchMyPostingSummary,
  fetchMyPostings,
  fetchPostings,
  transitionPosting,
} from "../../services/api";
import { useSession } from "../../components/auth/SessionProvider";

type Mode = "DISCOVER" | "MINE";

const POSTING_TYPES: PostingType[] = [
  "PROJECT",
  "THESIS_TOPIC",
  "COLLABORATION",
  "LAB_ROTATION",
  "INTERNSHIP",
  "RESEARCH_ASSISTANTSHIP",
  "POSTDOC",
];
const WORK_MODES: PostingWorkMode[] = ["ONSITE", "REMOTE", "HYBRID"];
const COMPENSATION_TYPES: CompensationType[] = [
  "UNSPECIFIED",
  "STIPEND",
  "SALARY",
  "HOURLY",
  "SCHOLARSHIP",
  "GRANT_FUNDED",
  "UNPAID",
];
const COMMITMENT_TYPES: CommitmentType[] = ["FULL_TIME", "PART_TIME", "FLEXIBLE"];
const COMPENSATION_PERIODS = ["MONTH", "YEAR", "WEEK", "HOUR", "TOTAL"];

const EMPTY_TERMS: OpeningTermsUpdate = {
  compensation_type: "UNSPECIFIED",
  accepts_applications: false,
};

const EMPTY_DRAFT: PostingCreatePayload = {
  title: "",
  posting_type: "PROJECT",
  description: "",
  summary: "",
  positions_available: 1,
  work_mode: "ONSITE",
};

export default function PostingsPage() {
  // Discovery is public, so this page is not guarded; only the authoring and "my
  // postings" controls need an account.
  const { status, hasRole } = useSession();
  const [mode, setMode] = useState<Mode>("DISCOVER");
  const [postings, setPostings] = useState<ResearchPosting[]>([]);
  const [summary, setSummary] = useState<PostingSummaryResponse | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Discovery filters
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<PostingType | "">("");
  const [workModeFilter, setWorkModeFilter] = useState<PostingWorkMode | "">("");
  const [acceptingOnly, setAcceptingOnly] = useState(false);

  // Authoring
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState<PostingCreatePayload>(EMPTY_DRAFT);
  const [skillsInput, setSkillsInput] = useState("");
  const [terms, setTerms] = useState<OpeningTermsUpdate>(EMPTY_TERMS);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Authoring is a faculty/admin capability. The server enforces this regardless; the UI
  // only avoids offering an action that would certainly be refused.
  const isSignedIn = status === "authenticated";
  const canAuthor = isSignedIn && hasRole("FACULTY", "ADMIN");

  useEffect(() => {
    if (!isSignedIn && mode === "MINE") setMode("DISCOVER");
  }, [isSignedIn, mode]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (mode === "MINE") {
        const [listed, summarized] = await Promise.all([
          fetchMyPostings({ limit: 50 }),
          fetchMyPostingSummary(),
        ]);
        setPostings(listed.postings);
        setTotal(listed.total);
        setSummary(summarized);
      } else {
        const filters: PostingFilterParams = {
          search: search.trim() || undefined,
          posting_type: typeFilter || undefined,
          work_mode: workModeFilter || undefined,
          accepting_only: acceptingOnly || undefined,
          limit: 50,
        };
        const listed = await fetchPostings(filters);
        setPostings(listed.postings);
        setTotal(listed.total);
        setSummary(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load research postings");
      setPostings([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [mode, search, typeFilter, workModeFilter, acceptingOnly]);

  useEffect(() => {
    load();
  }, [load]);

  const handleTransition = async (posting: ResearchPosting, target: PostingStatus) => {
    setBusyId(posting.id);
    setError(null);
    try {
      await transitionPosting(posting.id, target);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update posting status");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (posting: ResearchPosting) => {
    setBusyId(posting.id);
    setError(null);
    try {
      await deletePosting(posting.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete draft posting");
    } finally {
      setBusyId(null);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      const skills = skillsInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const isStructured = STRUCTURED_OPENING_TYPES.includes(draft.posting_type);
      await createPosting({
        ...draft,
        summary: draft.summary?.trim() || null,
        required_skills: skills,
        application_deadline: draft.application_deadline
          ? new Date(draft.application_deadline).toISOString()
          : null,
        // Appointment terms are only meaningful for funded openings. The server ignores them
        // for supervisor-led categories, so sending them would be misleading noise.
        opening_terms: isStructured ? terms : undefined,
      });
      setDraft(EMPTY_DRAFT);
      setSkillsInput("");
      setTerms(EMPTY_TERMS);
      setShowForm(false);
      setMode("MINE");
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create posting");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="postings-page">
      <header className="postings-header">
        <div className="postings-title-group">
          <h1>Research Postings</h1>
          <p className="postings-subtitle">
            Research openings posted directly by faculty on this platform: projects, available
            thesis topics, collaborations and lab rotations. Unlike ingested calls for papers,
            each posting has a named academic owner who is accountable for it.
          </p>
        </div>
        {canAuthor && (
          <button
            type="button"
            className="posting-btn primary"
            onClick={() => setShowForm((open) => !open)}
          >
            {showForm ? <X size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
            {showForm ? "Cancel" : "New posting"}
          </button>
        )}
      </header>

      <nav className="postings-mode-tabs" aria-label="Posting views">
        <button
          type="button"
          className={`postings-mode-tab${mode === "DISCOVER" ? " active" : ""}`}
          onClick={() => setMode("DISCOVER")}
        >
          Discover
        </button>
        {isSignedIn && (
          <>
            <button
              type="button"
              className={`postings-mode-tab${mode === "MINE" ? " active" : ""}`}
              onClick={() => setMode("MINE")}
            >
              My postings
            </button>
            <Link href="/postings/applications" className="postings-mode-tab">
              My applications
            </Link>
          </>
        )}
      </nav>

      {showForm && canAuthor && (
        <form className="posting-form" onSubmit={handleSubmit}>
          <div className="posting-field">
            <label htmlFor="posting-title">Title</label>
            <input
              id="posting-title"
              required
              minLength={5}
              maxLength={300}
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              placeholder="Doctoral position in neural information retrieval"
            />
          </div>

          <div className="posting-form-grid">
            <div className="posting-field">
              <label htmlFor="posting-type">Category</label>
              <select
                id="posting-type"
                value={draft.posting_type}
                onChange={(e) => setDraft({ ...draft, posting_type: e.target.value as PostingType })}
              >
                {POSTING_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {POSTING_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </div>
            <div className="posting-field">
              <label htmlFor="posting-work-mode">Work mode</label>
              <select
                id="posting-work-mode"
                value={draft.work_mode}
                onChange={(e) => setDraft({ ...draft, work_mode: e.target.value as PostingWorkMode })}
              >
                {WORK_MODES.map((m) => (
                  <option key={m} value={m}>
                    {WORK_MODE_LABELS[m]}
                  </option>
                ))}
              </select>
            </div>
            <div className="posting-field">
              <label htmlFor="posting-positions">Positions available</label>
              <input
                id="posting-positions"
                type="number"
                min={1}
                max={100}
                value={draft.positions_available ?? 1}
                onChange={(e) =>
                  setDraft({ ...draft, positions_available: Number(e.target.value) || 1 })
                }
              />
            </div>
            <div className="posting-field">
              <label htmlFor="posting-deadline">
                Application deadline <span className="posting-field-hint">optional, must be future</span>
              </label>
              <input
                id="posting-deadline"
                type="date"
                value={draft.application_deadline ?? ""}
                onChange={(e) =>
                  setDraft({ ...draft, application_deadline: e.target.value || null })
                }
              />
            </div>
            <div className="posting-field">
              <label htmlFor="posting-location">Location</label>
              <input
                id="posting-location"
                value={draft.location ?? ""}
                onChange={(e) => setDraft({ ...draft, location: e.target.value })}
                placeholder="Boston, US"
              />
            </div>
            <div className="posting-field">
              <label htmlFor="posting-country">
                Country <span className="posting-field-hint">2-letter code</span>
              </label>
              <input
                id="posting-country"
                maxLength={2}
                value={draft.country ?? ""}
                onChange={(e) => setDraft({ ...draft, country: e.target.value })}
                placeholder="US"
              />
            </div>
          </div>

          <div className="posting-field">
            <label htmlFor="posting-summary">
              Summary <span className="posting-field-hint">one line shown in listings</span>
            </label>
            <input
              id="posting-summary"
              maxLength={500}
              value={draft.summary ?? ""}
              onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
            />
          </div>

          <div className="posting-field">
            <label htmlFor="posting-description">Description</label>
            <textarea
              id="posting-description"
              required
              minLength={20}
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="Describe the research, what the appointee will do, and how to apply."
            />
          </div>

          <div className="posting-field">
            <label htmlFor="posting-skills">
              Required skills <span className="posting-field-hint">comma separated</span>
            </label>
            <input
              id="posting-skills"
              value={skillsInput}
              onChange={(e) => setSkillsInput(e.target.value)}
              placeholder="Python, PyTorch, Information Retrieval"
            />
          </div>

          {STRUCTURED_OPENING_TYPES.includes(draft.posting_type) && (
            <>
              <p className="posting-owner-note">
                This category is a funded appointment, so applicants will look for its terms.
                “Unpaid” is worth stating explicitly rather than leaving blank.
              </p>
              <div className="posting-form-grid">
                <div className="posting-field">
                  <label htmlFor="terms-compensation-type">Compensation</label>
                  <select
                    id="terms-compensation-type"
                    value={terms.compensation_type ?? "UNSPECIFIED"}
                    onChange={(e) =>
                      setTerms({ ...terms, compensation_type: e.target.value as CompensationType })
                    }
                  >
                    {COMPENSATION_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {COMPENSATION_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-amount">Amount</label>
                  <input
                    id="terms-amount"
                    type="number"
                    min={0}
                    value={terms.compensation_amount ?? ""}
                    onChange={(e) =>
                      setTerms({
                        ...terms,
                        compensation_amount: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-currency">
                    Currency <span className="posting-field-hint">3-letter code</span>
                  </label>
                  <input
                    id="terms-currency"
                    maxLength={3}
                    value={terms.compensation_currency ?? ""}
                    onChange={(e) =>
                      setTerms({ ...terms, compensation_currency: e.target.value || null })
                    }
                    placeholder="USD"
                  />
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-period">Per</label>
                  <select
                    id="terms-period"
                    value={terms.compensation_period ?? ""}
                    onChange={(e) =>
                      setTerms({ ...terms, compensation_period: e.target.value || null })
                    }
                  >
                    <option value="">Not specified</option>
                    {COMPENSATION_PERIODS.map((p) => (
                      <option key={p} value={p}>
                        {p.charAt(0) + p.slice(1).toLowerCase()}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-commitment">Commitment</label>
                  <select
                    id="terms-commitment"
                    value={terms.commitment_type ?? ""}
                    onChange={(e) =>
                      setTerms({
                        ...terms,
                        commitment_type: (e.target.value || null) as CommitmentType | null,
                      })
                    }
                  >
                    <option value="">Not specified</option>
                    {COMMITMENT_TYPES.map((c) => (
                      <option key={c} value={c}>
                        {COMMITMENT_TYPE_LABELS[c]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-hours">Hours per week</label>
                  <input
                    id="terms-hours"
                    type="number"
                    min={1}
                    max={80}
                    value={terms.hours_per_week ?? ""}
                    onChange={(e) =>
                      setTerms({
                        ...terms,
                        hours_per_week: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </div>
                <div className="posting-field">
                  <label htmlFor="terms-duration">Duration in months</label>
                  <input
                    id="terms-duration"
                    type="number"
                    min={1}
                    max={120}
                    value={terms.duration_months ?? ""}
                    onChange={(e) =>
                      setTerms({
                        ...terms,
                        duration_months: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </div>
              </div>

              <div className="posting-field">
                <label htmlFor="terms-eligibility">
                  Eligibility{" "}
                  <span className="posting-field-hint">enrolment, visa or degree requirements</span>
                </label>
                <textarea
                  id="terms-eligibility"
                  value={terms.eligibility_requirements ?? ""}
                  onChange={(e) =>
                    setTerms({ ...terms, eligibility_requirements: e.target.value || null })
                  }
                  style={{ minHeight: "70px" }}
                />
              </div>

              <label className="postings-checkbox">
                <input
                  type="checkbox"
                  checked={terms.accepts_applications ?? false}
                  onChange={(e) => setTerms({ ...terms, accepts_applications: e.target.checked })}
                />
                Accept applications through this platform
              </label>
            </>
          )}

          {formError && (
            <div className="postings-error" role="alert">
              <AlertCircle size={15} aria-hidden="true" />
              <span>{formError}</span>
            </div>
          )}

          <p className="posting-owner-note">
            The posting is saved as a draft. Publish it from “My postings” when you are ready
            for researchers to see it.
          </p>

          <div className="posting-form-actions">
            <button type="submit" className="posting-btn primary" disabled={submitting}>
              {submitting ? <Loader2 size={14} className="spin" aria-hidden="true" /> : null}
              Save draft
            </button>
            <button
              type="button"
              className="posting-btn"
              onClick={() => setShowForm(false)}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === "MINE" && summary && (
        <div className="postings-stats">
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.total}</div>
            <div className="postings-stat-label">Total</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.by_status.OPEN ?? 0}</div>
            <div className="postings-stat-label">Open</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.by_status.DRAFT ?? 0}</div>
            <div className="postings-stat-label">Drafts</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.open_accepting_applications}</div>
            <div className="postings-stat-label">Accepting now</div>
          </div>
        </div>
      )}

      {mode === "DISCOVER" && (
        <div className="postings-filters">
          <div className="postings-search">
            <Search size={14} className="postings-search-icon" aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search postings"
              aria-label="Search postings"
            />
          </div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as PostingType | "")}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            {POSTING_TYPES.map((t) => (
              <option key={t} value={t}>
                {POSTING_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          <select
            value={workModeFilter}
            onChange={(e) => setWorkModeFilter(e.target.value as PostingWorkMode | "")}
            aria-label="Filter by work mode"
          >
            <option value="">Any work mode</option>
            {WORK_MODES.map((m) => (
              <option key={m} value={m}>
                {WORK_MODE_LABELS[m]}
              </option>
            ))}
          </select>
          <label className="postings-checkbox">
            <input
              type="checkbox"
              checked={acceptingOnly}
              onChange={(e) => setAcceptingOnly(e.target.checked)}
            />
            Accepting applications
          </label>
          <button type="button" className="posting-btn" onClick={load} disabled={loading}>
            <RefreshCw size={13} aria-hidden="true" />
            Refresh
          </button>
        </div>
      )}

      {error && (
        <div className="postings-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="postings-loading">Loading research postings…</div>
      ) : postings.length === 0 ? (
        <div className="postings-empty">
          {mode === "MINE"
            ? "You have not authored any postings yet."
            : "No open research postings match these filters."}
        </div>
      ) : (
        <>
          <p className="postings-subtitle">
            {total} posting{total === 1 ? "" : "s"}
          </p>
          <div className="postings-list">
            {postings.map((posting) => (
              <PostingCard
                key={posting.id}
                posting={posting}
                showOwnerControls={mode === "MINE"}
                onTransition={handleTransition}
                onDelete={handleDelete}
                busy={busyId === posting.id}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
