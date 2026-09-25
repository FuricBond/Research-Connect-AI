"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "../../../styles/postings.css";
import { AlertCircle, ArrowLeft, RefreshCw } from "lucide-react";
import { ApplicationCard } from "../../../components/postings/ApplicationCard";
import type {
  ApplicationStatus,
  ApplicationSummaryResponse,
  PostingApplication,
} from "../../../types/posting";
import { APPLICATION_STATUS_LABELS } from "../../../types/posting";
import {
  fetchMyApplicationSummary,
  fetchMyApplications,
  transitionApplication,
} from "../../../services/api";

const STATUS_FILTERS: (ApplicationStatus | "")[] = [
  "",
  "SUBMITTED",
  "UNDER_REVIEW",
  "SHORTLISTED",
  "OFFERED",
  "ACCEPTED",
  "DECLINED",
  "REJECTED",
  "WITHDRAWN",
];

export default function MyApplicationsPage() {
  const [applications, setApplications] = useState<PostingApplication[]>([]);
  const [summary, setSummary] = useState<ApplicationSummaryResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listed, summarized] = await Promise.all([
        fetchMyApplications({ status: statusFilter || undefined, limit: 100 }),
        fetchMyApplicationSummary(),
      ]);
      setApplications(listed.applications);
      setSummary(summarized);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load your applications");
      setApplications([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleTransition = async (
    application: PostingApplication,
    target: ApplicationStatus
  ) => {
    setBusyId(application.id);
    setError(null);
    try {
      await transitionApplication(application.id, target);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update the application");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="postings-page">
      <Link href="/postings" className="posting-back-link">
        <ArrowLeft size={14} aria-hidden="true" />
        Back to postings
      </Link>

      <header className="postings-header">
        <div className="postings-title-group">
          <h1>My Applications</h1>
          <p className="postings-subtitle">
            Applications you have submitted to funded research openings. You can withdraw at any
            point, and respond once an offer is extended; review decisions rest with the posting’s
            author.
          </p>
        </div>
        <button type="button" className="posting-btn" onClick={load} disabled={loading}>
          <RefreshCw size={13} aria-hidden="true" />
          Refresh
        </button>
      </header>

      {summary && (
        <div className="postings-stats">
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.total}</div>
            <div className="postings-stat-label">Total</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.active}</div>
            <div className="postings-stat-label">Still in play</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.by_status.OFFERED ?? 0}</div>
            <div className="postings-stat-label">Offers</div>
          </div>
          <div className="postings-stat">
            <div className="postings-stat-value">{summary.by_status.ACCEPTED ?? 0}</div>
            <div className="postings-stat-label">Accepted</div>
          </div>
        </div>
      )}

      <div className="postings-filters">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ApplicationStatus | "")}
          aria-label="Filter by application status"
        >
          {STATUS_FILTERS.map((value) => (
            <option key={value || "ALL"} value={value}>
              {value ? APPLICATION_STATUS_LABELS[value] : "All statuses"}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="postings-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="postings-loading">Loading your applications…</div>
      ) : applications.length === 0 ? (
        <div className="postings-empty">
          You have not applied to any openings yet. Funded internships, assistantships and
          post-doctoral positions accept applications directly on this platform.
        </div>
      ) : (
        <div className="postings-list">
          {applications.map((application) => (
            <ApplicationCard
              key={application.id}
              application={application}
              onTransition={handleTransition}
              busy={busyId === application.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
