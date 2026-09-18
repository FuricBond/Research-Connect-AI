"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import "@/styles/submission.css";
import type {
  ResearchSubmission,
  ResearchSubmissionCreate,
  ResearchSubmissionUpdate,
  SubmissionStatus,
  SubmissionType,
} from "@/types/submission";
import type { WorkspaceItem } from "@/types/workspace";
import {
  createSubmission,
  deleteSubmission,
  fetchWorkspaceItems,
  fetchWorkspaceSubmissions,
  transitionSubmissionStatus,
  updateSubmission,
} from "@/services/api";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  Plus,
  Save,
  Send,
  Trash2,
  XCircle,
} from "lucide-react";

interface PageProps {
  params: Promise<{ id: string }>;
}

const SUBMISSION_TYPES: { label: string; value: SubmissionType }[] = [
  { label: "Full Paper", value: "FULL_PAPER" },
  { label: "Short Paper", value: "SHORT_PAPER" },
  { label: "Extended Abstract", value: "EXTENDED_ABSTRACT" },
  { label: "Poster", value: "POSTER" },
  { label: "Workshop Paper", value: "WORKSHOP_PAPER" },
  { label: "Grant Proposal", value: "GRANT_PROPOSAL" },
  { label: "Other", value: "OTHER" },
];

const LIFECYCLE_STEPS: { status: SubmissionStatus; label: string; stepNumber: number }[] = [
  { status: "DRAFT", label: "Draft", stepNumber: 1 },
  { status: "READY", label: "Ready", stepNumber: 2 },
  { status: "SUBMITTED", label: "Submitted", stepNumber: 3 },
  { status: "UNDER_REVIEW", label: "Under Review", stepNumber: 4 },
  { status: "ACCEPTED", label: "Decision", stepNumber: 5 },
];

function getStepState(
  stepStatus: SubmissionStatus,
  currentStatus: SubmissionStatus
): "completed" | "active" | "future" | "rejected" | "withdrawn" {
  if (currentStatus === "WITHDRAWN") return "withdrawn";

  const order: Record<SubmissionStatus, number> = {
    DRAFT: 1,
    READY: 2,
    SUBMITTED: 3,
    UNDER_REVIEW: 4,
    ACCEPTED: 5,
    REJECTED: 5,
    WITHDRAWN: 0,
  };

  const currentIdx = order[currentStatus] ?? 1;
  const stepIdx = order[stepStatus] ?? 1;

  if (stepStatus === "ACCEPTED") {
    if (currentStatus === "ACCEPTED") return "active";
    if (currentStatus === "REJECTED") return "rejected";
    return "future";
  }

  if (currentIdx > stepIdx) return "completed";
  if (currentIdx === stepIdx) return "active";
  return "future";
}

export default function SubmissionManagementPage({ params }: PageProps) {
  const { id: workspaceItemId } = React.use(params);

  const [workspaceItem, setWorkspaceItem] = useState<WorkspaceItem | null>(null);
  const [submissions, setSubmissions] = useState<ResearchSubmission[]>([]);
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Draft / edit state
  const [editForm, setEditForm] = useState<ResearchSubmissionUpdate>({});
  const [transitionNotes, setTransitionNotes] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSubmissionTitle, setNewSubmissionTitle] = useState("");
  const [newSubmissionType, setNewSubmissionType] = useState<SubmissionType>("FULL_PAPER");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch workspace items to find parent
      const wsRes = await fetchWorkspaceItems({ limit: 100, include_archived: true });
      const parent = wsRes.items.find((it: WorkspaceItem) => it.id === workspaceItemId) || null;
      setWorkspaceItem(parent);

      // 2. Fetch submissions for this workspace item
      const subsRes = await fetchWorkspaceSubmissions(workspaceItemId);
      setSubmissions(subsRes.items);

      if (subsRes.items.length > 0) {
        // Select first or keep existing selection
        const targetId =
          selectedSubId && subsRes.items.some((s: ResearchSubmission) => s.id === selectedSubId)
            ? selectedSubId
            : subsRes.items[0].id;
        setSelectedSubId(targetId);

        const currentSub = subsRes.items.find((s: ResearchSubmission) => s.id === targetId);
        if (currentSub) {
          setEditForm({
            title: currentSub.title,
            abstract: currentSub.abstract || "",
            submission_type: currentSub.submission_type,
            venue: currentSub.venue || "",
            external_submission_id: currentSub.external_submission_id || "",
            submission_url: currentSub.submission_url || "",
            notes: currentSub.notes || "",
          });
        }
      } else {
        setShowCreateForm(true);
        if (parent) {
          setNewSubmissionTitle(`Submission: ${parent.opportunity.title}`);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submission tracking");
    } finally {
      setLoading(false);
    }
  }, [workspaceItemId, selectedSubId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const activeSubmission = submissions.find((s) => s.id === selectedSubId) || null;

  // Handle switching selected submission attempt
  const handleSelectSubmission = (sub: ResearchSubmission) => {
    setSelectedSubId(sub.id);
    setShowCreateForm(false);
    setEditForm({
      title: sub.title,
      abstract: sub.abstract || "",
      submission_type: sub.submission_type,
      venue: sub.venue || "",
      external_submission_id: sub.external_submission_id || "",
      submission_url: sub.submission_url || "",
      notes: sub.notes || "",
    });
  };

  // Handle saving metadata updates
  const handleSaveMetadata = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSubmission) return;

    setIsSaving(true);
    setError(null);
    try {
      const updated = await updateSubmission(activeSubmission.id, editForm);
      setSubmissions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save submission metadata");
    } finally {
      setIsSaving(false);
    }
  };

  // Handle deterministic state transition
  const handleTransition = async (targetStatus: SubmissionStatus) => {
    if (!activeSubmission) return;

    setIsTransitioning(true);
    setError(null);
    try {
      const transitioned = await transitionSubmissionStatus(activeSubmission.id, {
        target_status: targetStatus,
        notes: transitionNotes.trim() || undefined,
      });
      setSubmissions((prev) => prev.map((s) => (s.id === transitioned.id ? transitioned : s)));
      setTransitionNotes("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status transition failed");
    } finally {
      setIsTransitioning(false);
    }
  };

  // Handle creating a new submission
  const handleCreateSubmission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubmissionTitle.trim()) return;

    setIsSaving(true);
    setError(null);
    try {
      const payload: ResearchSubmissionCreate = {
        workspace_item_id: workspaceItemId,
        title: newSubmissionTitle.trim(),
        submission_type: newSubmissionType,
      };
      const created = await createSubmission(payload);
      setSubmissions((prev) => [created, ...prev]);
      setSelectedSubId(created.id);
      setShowCreateForm(false);
      setEditForm({
        title: created.title,
        abstract: "",
        submission_type: created.submission_type,
        venue: "",
        external_submission_id: "",
        submission_url: "",
        notes: "",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create submission draft");
    } finally {
      setIsSaving(false);
    }
  };

  // Handle deleting draft or withdrawn submission
  const handleDeleteSubmission = async () => {
    if (!activeSubmission) return;
    if (!confirm(`Are you sure you want to delete "${activeSubmission.title}"?`)) return;

    setIsSaving(true);
    setError(null);
    try {
      await deleteSubmission(activeSubmission.id);
      const remaining = submissions.filter((s) => s.id !== activeSubmission.id);
      setSubmissions(remaining);
      if (remaining.length > 0) {
        handleSelectSubmission(remaining[0]);
      } else {
        setSelectedSubId(null);
        setShowCreateForm(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete submission");
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="submission-container">
        <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", padding: "40px 0" }}>
          <Loader2 className="animate-spin" size={18} /> Loading submission tracking...
        </div>
      </div>
    );
  }

  const opp = workspaceItem?.opportunity;
  const deadlineCtx = activeSubmission?.deadline_context;

  return (
    <div className="submission-container">
      {/* ── Navigation ── */}
      <Link href="/workspace" className="submission-back-link">
        <ArrowLeft size={14} /> Back to Opportunity Workspace
      </Link>

      {/* ── Error Banner ── */}
      {error && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "#fee2e2",
            border: "1px solid #fca5a5",
            color: "#b91c1c",
            borderRadius: "var(--radius-md)",
            padding: "12px 16px",
            marginBottom: "20px",
            fontSize: "13px",
          }}
        >
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* ── Header: Parent Opportunity ── */}
      <div className="submission-header">
        <div className="submission-header-top">
          <div>
            <h1 className="submission-opp-title">{opp?.title || "Opportunity Workspace Item"}</h1>
            <div className="submission-opp-meta">
              <span className="submission-opp-meta-item">
                <Globe size={13} /> {opp?.publisher || opp?.organizer || "Independent Venue"}
              </span>
              <span className="submission-opp-meta-item">
                <FileText size={13} /> {opp?.opportunity_type || "CONFERENCE"}
              </span>
              <span className="submission-opp-meta-item">
                Workspace Status: <strong>{workspaceItem?.status || "PLANNING"}</strong>
              </span>
            </div>
          </div>

          <button
            onClick={() => setShowCreateForm(true)}
            className="btn-save"
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
          >
            <Plus size={14} /> New Submission Attempt
          </button>
        </div>
      </div>

      {/* ── Deadline Intelligence Banner ── */}
      {deadlineCtx && deadlineCtx.submission_deadline && (
        <div
          className={`submission-deadline-alert ${
            deadlineCtx.urgency_tier === "CRITICAL"
              ? "critical"
              : deadlineCtx.urgency_tier === "URGENT" || deadlineCtx.urgency_tier === "APPROACHING"
              ? "approaching"
              : ""
          }`}
        >
          <div className="deadline-left">
            <Clock className="deadline-icon" />
            <div className="deadline-details">
              <h4>
                Official Submission Deadline:{" "}
                {new Date(deadlineCtx.submission_deadline).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </h4>
              <p>
                {deadlineCtx.days_remaining !== null && deadlineCtx.days_remaining !== undefined
                  ? `${Math.round(deadlineCtx.days_remaining)} days remaining until manuscript cutoff.`
                  : "Deadline date confirmed from official CFPs."}
                {deadlineCtx.summary && ` ${deadlineCtx.summary}`}
              </p>
            </div>
          </div>

          <div className="deadline-badges">
            {deadlineCtx.is_aoe && <span className="badge-aoe">AoE Anywhere on Earth</span>}
            {deadlineCtx.has_extension && <span className="badge-extension">Deadline Extended</span>}
            {deadlineCtx.urgency_tier && (
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: "var(--bg-main)",
                  border: "1px solid var(--border-color)",
                }}
              >
                {deadlineCtx.urgency_tier}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── New Submission Form Modal / Card ── */}
      {showCreateForm && (
        <div className="submission-card" style={{ border: "2px solid var(--color-primary)" }}>
          <h2 className="submission-card-title">Create New Research Submission Draft</h2>
          <form onSubmit={handleCreateSubmission}>
            <div className="form-group">
              <label className="form-label">Manuscript / Proposal Title *</label>
              <input
                type="text"
                required
                value={newSubmissionTitle}
                onChange={(e) => setNewSubmissionTitle(e.target.value)}
                placeholder="e.g. Robust Representation Learning via Contrastive Masking"
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Submission Format</label>
              <select
                value={newSubmissionType}
                onChange={(e) => setNewSubmissionType(e.target.value as SubmissionType)}
                className="form-select"
              >
                {SUBMISSION_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="btn-action-row">
              <button type="submit" disabled={isSaving} className="btn-save">
                {isSaving ? <Loader2 size={13} className="animate-spin" /> : "Create Draft"}
              </button>
              {submissions.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="workspace-action-btn"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      {/* ── Active Submission View ── */}
      {activeSubmission && !showCreateForm && (
        <>
          {/* ── Visual Stepper Pipeline ── */}
          <div className="submission-pipeline-card">
            <div className="pipeline-title">
              Submission Lifecycle Pipeline — Status:{" "}
              <span className={`status-badge ${activeSubmission.status.toLowerCase()}`}>
                {activeSubmission.status}
              </span>
            </div>

            <div className="submission-stepper">
              {LIFECYCLE_STEPS.map((step) => {
                const state = getStepState(step.status, activeSubmission.status);
                return (
                  <div key={step.status} className={`stepper-step ${state}`}>
                    <div className="stepper-circle">
                      {state === "completed" ? (
                        <CheckCircle2 size={16} />
                      ) : state === "rejected" ? (
                        <XCircle size={16} />
                      ) : (
                        step.stepNumber
                      )}
                    </div>
                    <span className="stepper-label">
                      {step.status === "ACCEPTED" && activeSubmission.status === "REJECTED"
                        ? "Rejected"
                        : step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Main Content Grid ── */}
          <div className="submission-content-grid">
            {/* ── Left Column: Metadata & Details ── */}
            <div>
              <div className="submission-card">
                <h3 className="submission-card-title">
                  <span>Manuscript & Submission Details</span>
                  <span className={`status-badge ${activeSubmission.status.toLowerCase()}`}>
                    {activeSubmission.status}
                  </span>
                </h3>

                <form onSubmit={handleSaveMetadata}>
                  <div className="form-group">
                    <label className="form-label">Manuscript Title</label>
                    <input
                      type="text"
                      required
                      value={editForm.title || ""}
                      onChange={(e) => setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, title: e.target.value }))}
                      className="form-input"
                    />
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">Submission Type</label>
                      <select
                        value={editForm.submission_type || "FULL_PAPER"}
                        onChange={(e) =>
                          setEditForm((prev: ResearchSubmissionUpdate) => ({
                            ...prev,
                            submission_type: e.target.value as SubmissionType,
                          }))
                        }
                        className="form-select"
                      >
                        {SUBMISSION_TYPES.map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Venue / Track Name</label>
                      <input
                        type="text"
                        value={editForm.venue || ""}
                        onChange={(e) => setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, venue: e.target.value }))}
                        placeholder={opp?.title || "e.g. Main Track / Oral"}
                        className="form-input"
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">External Submission / Paper ID</label>
                      <input
                        type="text"
                        value={editForm.external_submission_id || ""}
                        onChange={(e) =>
                          setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, external_submission_id: e.target.value }))
                        }
                        placeholder="e.g. OPENREVIEW-9811, CMT #45"
                        className="form-input"
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Portal / Tracking URL</label>
                      <div style={{ display: "flex", gap: "6px" }}>
                        <input
                          type="url"
                          value={editForm.submission_url || ""}
                          onChange={(e) =>
                            setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, submission_url: e.target.value }))
                          }
                          placeholder="https://openreview.net/forum?id=..."
                          className="form-input"
                        />
                        {editForm.submission_url && (
                          <a
                            href={editForm.submission_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="workspace-action-btn"
                            title="Open submission portal"
                            style={{ display: "inline-flex", alignItems: "center", padding: "0 10px" }}
                          >
                            <ExternalLink size={14} />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Abstract</label>
                    <textarea
                      value={editForm.abstract || ""}
                      onChange={(e) =>
                        setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, abstract: e.target.value }))
                      }
                      placeholder="Paste manuscript abstract or proposal summary..."
                      className="form-textarea"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Notes & Reviewer Comments</label>
                    <textarea
                      value={editForm.notes || ""}
                      onChange={(e) => setEditForm((prev: ResearchSubmissionUpdate) => ({ ...prev, notes: e.target.value }))}
                      placeholder="Notes on co-author tasks, rebuttal timeline, or reviewer feedback..."
                      className="form-textarea"
                      style={{ minHeight: "80px" }}
                    />
                  </div>

                  <div className="btn-action-row">
                    <button
                      type="submit"
                      disabled={isSaving}
                      className="btn-save"
                      style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                    >
                      {isSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                      Save Metadata
                    </button>

                    {(activeSubmission.status === "DRAFT" || activeSubmission.status === "WITHDRAWN") && (
                      <button
                        type="button"
                        onClick={handleDeleteSubmission}
                        disabled={isSaving}
                        className="btn-delete-sub"
                        style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                      >
                        <Trash2 size={13} /> Delete Submission
                      </button>
                    )}
                  </div>
                </form>
              </div>
            </div>

            {/* ── Right Column: Lifecycle Actions & Attempts ── */}
            <div>
              {/* ── Transition Actions ── */}
              <div className="submission-card">
                <h3 className="submission-card-title">Workflow Actions</h3>

                <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 14px 0" }}>
                  Deterministic state transitions available from{" "}
                  <strong>{activeSubmission.status}</strong>:
                </p>

                {activeSubmission.allowed_transitions.length > 0 ? (
                  <div className="transition-actions-panel">
                    <div className="form-group" style={{ marginBottom: "12px" }}>
                      <label className="form-label" style={{ fontSize: "12px" }}>
                        Transition Notes (optional)
                      </label>
                      <input
                        type="text"
                        value={transitionNotes}
                        onChange={(e) => setTransitionNotes(e.target.value)}
                        placeholder="e.g. Submitted via OpenReview #9811"
                        className="form-input"
                        style={{ fontSize: "12px", padding: "6px 10px" }}
                      />
                    </div>

                    {activeSubmission.allowed_transitions.map((nextStatus: SubmissionStatus) => {
                      const isPromote = nextStatus === "SUBMITTED" || nextStatus === "ACCEPTED";
                      const isWithdraw = nextStatus === "WITHDRAWN";
                      const isReject = nextStatus === "REJECTED";

                      return (
                        <button
                          key={nextStatus}
                          onClick={() => handleTransition(nextStatus)}
                          disabled={isTransitioning}
                          className={`btn-transition ${
                            isPromote ? "primary" : isReject ? "danger" : isWithdraw ? "" : "success"
                          }`}
                        >
                          <span>Move to {nextStatus}</span>
                          {isTransitioning ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Send size={13} />
                          )}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                    No valid forward transitions available from this state.
                  </p>
                )}

                {activeSubmission.status === "SUBMITTED" && activeSubmission.submitted_at && (
                  <div
                    style={{
                      marginTop: "16px",
                      padding: "10px",
                      background: "rgba(16, 185, 129, 0.08)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "12px",
                      color: "#065f46",
                    }}
                  >
                    Officially submitted on:{" "}
                    <strong>{new Date(activeSubmission.submitted_at).toLocaleDateString()}</strong>
                  </div>
                )}

                {activeSubmission.decision_at && (
                  <div
                    style={{
                      marginTop: "10px",
                      padding: "10px",
                      background: "rgba(59, 130, 246, 0.08)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "12px",
                      color: "#1e40af",
                    }}
                  >
                    Decision recorded on:{" "}
                    <strong>{new Date(activeSubmission.decision_at).toLocaleDateString()}</strong>
                  </div>
                )}
              </div>

              {/* ── Submission Attempts List ── */}
              {submissions.length > 1 && (
                <div className="submission-card">
                  <h3 className="submission-card-title">All Attempts for Opportunity</h3>
                  <div className="submission-attempts-list">
                    {submissions.map((sub) => (
                      <div
                        key={sub.id}
                        onClick={() => handleSelectSubmission(sub)}
                        className={`submission-attempt-card ${
                          sub.id === activeSubmission.id ? "selected" : ""
                        }`}
                      >
                        <div className="attempt-header">
                          <h4 className="attempt-title">{sub.title}</h4>
                          <span className={`status-badge ${sub.status.toLowerCase()}`}>
                            {sub.status}
                          </span>
                        </div>
                        <div className="attempt-meta">
                          {sub.submission_type} • Updated{" "}
                          {new Date(sub.updated_at).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
