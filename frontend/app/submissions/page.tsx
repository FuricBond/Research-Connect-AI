"use client";

/**
 * Submissions — every manuscript the signed-in researcher is tracking, across all workspace
 * items (Phase 4.2). Each submission is managed on its workspace item's submission page; this
 * overview lists them in one place with their status and deadline.
 */
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../styles/workspace.css";
import { AlertCircle, ArrowRight, Calendar, FileText, Loader2, RefreshCw } from "lucide-react";
import { RequireAuth } from "../../components/auth/RequireAuth";
import { fetchSubmissions, fetchSubmissionSummary } from "../../services/api";
import type {
  ResearchSubmission,
  SubmissionStatus,
  SubmissionSummaryResponse,
} from "../../types/submission";

const STATUS_LABELS: Record<SubmissionStatus, string> = {
  DRAFT: "Draft",
  READY: "Ready",
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under review",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
};

// Reuses the workspace status colours: early stages, in flight, and final outcomes.
const STATUS_BADGE: Record<SubmissionStatus, string> = {
  DRAFT: "status-badge-planning",
  READY: "status-badge-considering",
  SUBMITTED: "status-badge-applied",
  UNDER_REVIEW: "status-badge-considering",
  ACCEPTED: "status-badge-accepted",
  REJECTED: "status-badge-rejected",
  WITHDRAWN: "status-badge-archived",
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function humanize(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, " ");
}

function SubmissionsPage() {
  const [items, setItems] = useState<ResearchSubmission[]>([]);
  const [summary, setSummary] = useState<SubmissionSummaryResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, stats] = await Promise.all([
        fetchSubmissions({ status: statusFilter || undefined, sort_by: "updated_at", sort_order: "desc", limit: 100 }),
        fetchSubmissionSummary(),
      ]);
      setItems(list.items);
      setSummary(stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submissions.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="workspace-container">
      <div className="workspace-header">
        <div className="workspace-header-top">
          <div className="workspace-title-wrap">
            <h1>Submissions</h1>
            <p className="workspace-tagline">
              Every manuscript you are tracking, from first draft to decision, with its target deadline.
            </p>
          </div>
          <button onClick={() => void loadData()} className="workspace-action-btn" disabled={loading}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>

        {summary && (
          <div className="workspace-stats-strip">
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Total</span>
              <span className="workspace-stat-value">{summary.total_submissions}</span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">In progress</span>
              <span className="workspace-stat-value">{summary.active_submissions}</span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Accepted</span>
              <span className="workspace-stat-value">{summary.accepted_submissions}</span>
            </div>
            <div className="workspace-stat-card">
              <span className="workspace-stat-label">Rejected</span>
              <span className="workspace-stat-value">{summary.rejected_submissions}</span>
            </div>
          </div>
        )}
      </div>

      <div className="workspace-controls">
        <select
          className="workspace-select"
          aria-label="Filter by submission status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as SubmissionStatus | "")}
        >
          <option value="">All statuses</option>
          {(Object.keys(STATUS_LABELS) as SubmissionStatus[]).map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="workspace-error-banner" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="workspace-empty-state">
          <Loader2 size={24} className="spin" />
          <p>Loading submissions…</p>
        </div>
      ) : items.length === 0 && !error ? (
        <div className="workspace-empty-state">
          <FileText size={28} />
          <h3>No submissions yet</h3>
          <p>Start a submission from an opportunity in your workspace to track it here.</p>
          <Link href="/workspace" className="workspace-action-btn primary">
            Open workspace <ArrowRight size={14} />
          </Link>
        </div>
      ) : (
        <div className="workspace-list">
          {items.map((submission) => {
            const deadline = submission.deadline_context;
            return (
              <div className="workspace-card" key={submission.id}>
                <div className="workspace-card-top">
                  <div className="workspace-card-title-area">
                    <div className="workspace-card-badges">
                      <span className={`workspace-status-badge ${STATUS_BADGE[submission.status]}`}>
                        {STATUS_LABELS[submission.status]}
                      </span>
                      <span className="workspace-tag-chip">{humanize(submission.submission_type)}</span>
                    </div>
                    <h3 className="workspace-card-title">{submission.title}</h3>
                    <div className="workspace-card-meta">
                      <span>{submission.venue_name || submission.venue || submission.opportunity_title}</span>
                      {deadline?.submission_deadline && (
                        <span>
                          <Calendar size={13} /> Deadline {formatDate(deadline.submission_deadline)}
                          {typeof deadline.days_remaining === "number" && deadline.days_remaining >= 0
                            ? ` · ${Math.floor(deadline.days_remaining)} days left`
                            : ""}
                        </span>
                      )}
                      <span>Updated {formatDate(submission.updated_at)}</span>
                    </div>
                  </div>
                  <div className="workspace-card-actions">
                    <Link
                      href={`/workspace/${submission.workspace_item_id}/submission`}
                      className="workspace-action-btn primary"
                    >
                      Open <ArrowRight size={14} />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function SubmissionsRoute() {
  return (
    <RequireAuth>
      <SubmissionsPage />
    </RequireAuth>
  );
}
